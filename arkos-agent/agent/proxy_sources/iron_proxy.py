"""iron-proxy (``ironsh/iron-proxy``) integration for credential-injecting egress control.

Sandboxes (Docker/Modal/SSH) hold only opaque proxy tokens; iron-proxy — a TLS-intercepting,
default-deny egress firewall — swaps them for real credentials on the way out, so a leaked
token is useless outside the trusted proxy boundary.  The pinned binary is auto-installed
into ``<arkos_home>/bin``; CA, ``proxy.yaml``, ``mappings.json``, pidfile and logs live in
``<arkos_home>/proxy``.  Failures warn and never block agent startup.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import platform
import shutil
import signal
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_IRON_PROXY_VERSION = "0.39.0"
_IRON_PROXY_RELEASE_BASE = f"https://github.com/ironsh/iron-proxy/releases/download/v{_IRON_PROXY_VERSION}"
_IRON_PROXY_CHECKSUM_NAME = "checksums.txt"
_IRON_PROXY_CHECKSUM_SIG_NAME = "checksums.txt.asc"
_IRON_PROXY_PUBKEY_NAME = "public-key.asc"

_DOWNLOAD_TIMEOUT = 120
_RUN_TIMEOUT = 30
_STARTUP_GRACE_SECONDS = 5

_MGMT_API_KEY_ENV = "ARKOS_IRON_PROXY_MGMT_KEY"
_MGMT_PORT_OFFSET = 2
_MGMT_RELOAD_TIMEOUT = 15

_DEFAULT_TUNNEL_PORT = 9090

_DEFAULT_ALLOWED_HOSTS: Tuple[str, ...] = (
    "openrouter.ai", "*.openrouter.ai", "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com",
    "api.x.ai", "api.mistral.ai", "api.groq.com", "api.together.xyz", "api.deepseek.com",
)

_BEARER_PROVIDERS: Dict[str, Tuple[str, ...]] = {
    "OPENROUTER_API_KEY": ("openrouter.ai", "*.openrouter.ai"), "OPENAI_API_KEY": ("api.openai.com",),
    "GROQ_API_KEY": ("api.groq.com",), "TOGETHER_API_KEY": ("api.together.xyz",),
    "DEEPSEEK_API_KEY": ("api.deepseek.com",), "MISTRAL_API_KEY": ("api.mistral.ai",),
    "XAI_API_KEY": ("api.x.ai",),
}

_HEADER_AUTH_PROVIDERS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "ANTHROPIC_API_KEY": {"hosts": ("api.anthropic.com",), "match_headers": ("x-api-key", "Authorization"), "aliases": ()},
    "AZURE_OPENAI_API_KEY": {"hosts": ("*.openai.azure.com", "*.cognitiveservices.azure.com", "*.services.ai.azure.com"),
                             "match_headers": ("api-key", "Authorization"), "aliases": ()},
    "GEMINI_API_KEY": {"hosts": ("generativelanguage.googleapis.com",), "match_headers": ("x-goog-api-key",), "aliases": ("GOOGLE_API_KEY",)},
}

_NON_BEARER_PROVIDERS: Tuple[str, ...] = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "GOOGLE_APPLICATION_CREDENTIALS")

_DEFAULT_UPSTREAM_DENY_CIDRS: Tuple[str, ...] = (
    "127.0.0.0/8", "::1/128",
    "169.254.0.0/16", "fe80::/10",
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
    "::ffff:0:0/96",
    "100.64.0.0/10",
    "198.18.0.0/15",
)

_PROXY_SUBPROCESS_ENV_ALLOWLIST: Tuple[str, ...] = (
    "PATH", "HOME", "TMPDIR", "TZ", "LANG", "LC_ALL", "LC_CTYPE", "NO_COLOR", "SSL_CERT_DIR", "SSL_CERT_FILE", "SYSTEMROOT", "USERPROFILE",
)

_PROXY_SUBPROCESS_ENV_STRIP: Tuple[str, ...] = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy")

_KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

_VERSION_CACHE: Dict[str, str] = {}

_ARKOS_IRON_PROXY_NONCE_ENV = "ARKOS_IRON_PROXY_NONCE"
_proxy_nonce: Optional[str] = None


@dataclass
class ProxyStatus:
    enabled: bool = False
    binary_path: Optional[Path] = None
    binary_version: Optional[str] = None
    config_path: Optional[Path] = None
    ca_cert_path: Optional[Path] = None
    pid: Optional[int] = None
    listening: bool = False
    tunnel_port: int = _DEFAULT_TUNNEL_PORT
    warnings: List[str] = field(default_factory=list)

    @property
    def installed(self) -> bool:
        return self.binary_path is not None and self.binary_path.exists()

    @property
    def configured(self) -> bool:
        return bool(self.config_path and self.config_path.exists() and self.ca_cert_path and self.ca_cert_path.exists())


@dataclass
class TokenMapping:
    """Sandbox-visible proxy token -> upstream credential lookup.  ``real_env_name`` is read from iron-proxy's
    OWN env at egress; ``alias_env_names`` are extra SANDBOX names for the same token."""
    proxy_token: str
    real_env_name: str
    upstream_hosts: Tuple[str, ...]
    match_headers: Tuple[str, ...] = ("Authorization",)
    alias_env_names: Tuple[str, ...] = ()


def _arkos_bin_dir() -> Path:
    from arkos_constants import get_arkos_home
    return get_arkos_home() / "bin"


def _proxy_state_dir_ro() -> Path:
    from arkos_constants import get_arkos_home
    return get_arkos_home() / "proxy"


def _proxy_state_dir() -> Path:
    """Proxy state dir (CA key, pidfile, logs), created 0o700; unconditional chmod tightens a pre-existing slack-umask dir."""
    (d := _proxy_state_dir_ro()).mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        d.chmod(0o700)
    return d


def _platform_binary_name() -> str:
    return "iron-proxy.exe" if platform.system() == "Windows" else "iron-proxy"


def _platform_asset_name() -> str:
    """Map (uname, arch) -> ``iron-proxy_<version>_<os>_<arch>.tar.gz``; no Windows builds upstream."""
    system, machine = platform.system(), platform.machine().lower()
    if os_name := {"Linux": "linux", "Darwin": "darwin"}.get(system):
        arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
        return f"iron-proxy_{_IRON_PROXY_VERSION}_{os_name}_{arch}.tar.gz"
    if system == "Windows":
        raise RuntimeError(f"iron-proxy does not ship native Windows binaries as of v{_IRON_PROXY_VERSION}. Run the proxy on a Linux/macOS host, or inside WSL.")
    raise RuntimeError(f"Unsupported platform for iron-proxy auto-install: {system} {machine}")


def find_iron_proxy(*, install_if_missing: bool = False) -> Optional[Path]:
    """Managed ``<arkos_home>/bin`` copy first, then PATH; optionally auto-install."""
    managed = _arkos_bin_dir() / _platform_binary_name()
    if managed.exists() and os.access(managed, os.X_OK):
        return managed
    if system := shutil.which("iron-proxy"):
        return Path(system)
    if not install_if_missing:
        return None
    try:
        return install_iron_proxy()
    except Exception as exc:  # noqa: BLE001 — never block startup
        logger.warning("iron-proxy auto-install failed: %s", exc)
        return None


def install_iron_proxy(*, force: bool = False) -> Path:
    """Download, verify, and install the pinned binary; raises on any failure."""
    (bin_dir := _arkos_bin_dir()).mkdir(parents=True, exist_ok=True)
    target = bin_dir / _platform_binary_name()
    if target.exists() and not force:
        return target
    asset_name = _platform_asset_name()
    with tempfile.TemporaryDirectory(prefix="arkos-iron-proxy-") as tmpdir:
        archive_path, checksum_path = (tmp := Path(tmpdir)) / asset_name, tmp / _IRON_PROXY_CHECKSUM_NAME
        logger.info("Downloading %s", f"{_IRON_PROXY_RELEASE_BASE}/{asset_name}")
        _release_asset(asset_name, archive_path)
        _release_asset(_IRON_PROXY_CHECKSUM_NAME, checksum_path)
        _verify_checksums_signature(tmp, checksum_path)
        expected, actual = _expected_sha256(checksum_path, asset_name), _sha256_file(archive_path)
        if expected.lower() != actual.lower():
            raise RuntimeError(f"Checksum mismatch for {asset_name}: expected {expected}, got {actual}")
        with tarfile.open(archive_path, "r:gz") as tf:
            member = _pick_tar_member(tf, _platform_binary_name())
            try:
                tf.extract(member, tmp, filter="data")  # noqa: S202
            except TypeError:
                tf.extract(member, tmp)  # noqa: S202
            extracted = tmp / member.name
        fd, staged = tempfile.mkstemp(dir=str(bin_dir), prefix=".iron-proxy_")
        os.close(fd)
        shutil.copy2(extracted, staged)
        os.chmod(staged, 0o755)
        os.replace(staged, target)
    _VERSION_CACHE.pop(str(target), None)
    logger.info("Installed iron-proxy %s at %s", _IRON_PROXY_VERSION, target)
    return target


def _release_asset(name: str, dest: Path) -> None:
    """Download one pinned-release asset to ``dest``; RuntimeError on any URL error."""
    url = f"{_IRON_PROXY_RELEASE_BASE}/{name}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "arkos-agent"})
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp, open(dest, "wb") as f:  # noqa: S310
            shutil.copyfileobj(resp, f)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc


def _verify_checksums_signature(tmp: Path, checksum_path: Path) -> bool:
    """Best-effort GPG check of checksums.txt in an ephemeral keyring.  False (with a warning) when gpg or the signature
    assets are unavailable — SHA-256 stays enforced, gpg is never a hard dependency.  Raises ONLY on a present-but-bad signature."""
    if not (gpg := shutil.which("gpg")):
        logger.warning("gpg not found on PATH — skipping iron-proxy release-signature verification (SHA-256 checksum check still enforced).")
        return False
    sig_path, pubkey_path = tmp / _IRON_PROXY_CHECKSUM_SIG_NAME, tmp / _IRON_PROXY_PUBKEY_NAME
    try:
        _release_asset(_IRON_PROXY_CHECKSUM_SIG_NAME, sig_path)
        _release_asset(_IRON_PROXY_PUBKEY_NAME, pubkey_path)
    except RuntimeError as exc:
        logger.warning("iron-proxy release signature assets unavailable (%s) — skipping GPG verification (SHA-256 checksum check still enforced).", exc)
        return False
    (gnupg_home := tmp / "gnupg").mkdir(mode=0o700, exist_ok=True)
    gpg_base = [gpg, "--homedir", str(gnupg_home), "--batch", "--no-tty"]
    if (imp := _run([*gpg_base, "--import", str(pubkey_path)], timeout=60)).returncode != 0:
        logger.warning("Could not import iron-proxy signing key — skipping GPG verification (SHA-256 still enforced): %s", imp.stderr.decode("utf-8", "replace")[:200])
        return False
    if (verify := _run([*gpg_base, "--verify", str(sig_path), str(checksum_path)], timeout=60)).returncode != 0:
        raise RuntimeError(
            f"iron-proxy checksums.txt failed GPG signature verification — refusing to install (possible release-channel tampering). gpg: {verify.stderr.decode('utf-8', 'replace')[:300]}"
        )
    logger.info("Verified iron-proxy checksums.txt GPG signature.")
    return True


def _expected_sha256(checksum_file: Path, asset_name: str) -> str:
    """Parse ``sha256sum`` output (``<hex>  <filename>``)."""
    for line in checksum_file.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1] == asset_name:
            return parts[0]
    raise RuntimeError(f"No checksum entry for {asset_name} in {checksum_file.name}")


def _sha256_file(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _pick_tar_member(tf: tarfile.TarFile, binary_name: str) -> tarfile.TarInfo:
    """Find the binary in the archive (flat or one dir deep); reject abs paths and ``..``."""
    candidates = [
        m for m in tf.getmembers() if m.isfile() and not m.name.startswith("/") and ".." not in Path(m.name).parts and Path(m.name).name == binary_name
    ]
    if not candidates:
        raise RuntimeError(f"Could not find {binary_name} inside downloaded archive (members: {[m.name for m in tf.getmembers()[:5]]}...)")
    return min(candidates, key=lambda m: len(m.name))


def _allowlisted_env() -> Dict[str, str]:
    """Infrastructure-only env (PATH, HOME, locale) — never the operator's secrets."""
    return {n: os.environ[n] for n in _PROXY_SUBPROCESS_ENV_ALLOWLIST if n in os.environ}


def _run(argv: List[str], *, timeout: int, text: bool = False, **kwargs) -> "subprocess.CompletedProcess":
    if text:
        kwargs.update(text=True, encoding="utf-8", errors="replace")
    return subprocess.run(argv, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, **kwargs)  # noqa: S603


def iron_proxy_version(binary: Path) -> str:
    """``iron-proxy --version`` output, stripped and cached by path.  Empty on failure."""
    if (key := str(binary)) in _VERSION_CACHE:
        return _VERSION_CACHE[key]
    try:
        res = _run([str(binary), "--version"], timeout=_RUN_TIMEOUT, text=True, env=_allowlisted_env())
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if out := (res.stdout or res.stderr or "").strip():
        _VERSION_CACHE[key] = out
    return out


def _write_private_file(path: Path, data: bytes) -> None:
    """Create/truncate ``path`` 0o600 from the first byte (no chmod-after TOCTOU), O_NOFOLLOW against a planted
    symlink, fchmod to tighten a pre-existing file."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW, 0o600)
    try:
        with suppress(OSError, AttributeError):
            os.fchmod(fd, 0o600)
        os.write(fd, data)
    finally:
        os.close(fd)


def _fd_owned_by_us(fd: int) -> bool:
    """False iff the open file is owned by another uid (same threat model as the pidfile)."""
    try:
        st = os.fstat(fd)
        return not (hasattr(os, "getuid") and st.st_uid != os.getuid())
    except AttributeError:
        return True


def ensure_ca_cert(*, force: bool = False) -> Tuple[Path, Path]:
    """Generate (or return existing) 10-year CA cert + key via the host ``openssl``."""
    state = _proxy_state_dir()
    ca_crt, ca_key = state / "ca.crt", state / "ca.key"
    if ca_crt.exists() and ca_key.exists() and not force:
        return ca_crt, ca_key
    if shutil.which("openssl") is None:
        raise RuntimeError("openssl not found on PATH. Install OpenSSL (apt: `openssl`, brew: `openssl`) to generate the iron-proxy CA cert.")
    with tempfile.TemporaryDirectory(prefix="arkos-proxy-ca-") as tmpdir:
        tmp_key, tmp_crt = Path(tmpdir) / "ca.key", Path(tmpdir) / "ca.crt"
        _run(["openssl", "genrsa", "-out", str(tmp_key), "4096"], timeout=60, check=True)
        _run(["openssl", "req", "-x509", "-new", "-nodes", "-key", str(tmp_key), "-sha256", "-days", "3650", "-subj", "/CN=arkos iron-proxy CA",
              "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign", "-out", str(tmp_crt)], timeout=60, check=True)
        key_staged = ca_key.with_suffix(ca_key.suffix + ".staged")
        key_staged.unlink(missing_ok=True)
        _write_private_file(key_staged, tmp_key.read_bytes())
        os.replace(key_staged, ca_key)
        ca_crt.write_bytes(tmp_crt.read_bytes())
        os.chmod(ca_crt, 0o644)
    logger.info("Generated iron-proxy CA at %s", ca_crt)
    return ca_crt, ca_key


def mint_proxy_token(prefix: str = "arkos-proxy") -> str:
    """Opaque token: recognizable prefix + 128-bit random hex suffix (iron-proxy matches exactly)."""
    return f"{prefix}-{hashlib.sha256(os.urandom(32)).hexdigest()[:32]}"


def _read_text_or_none(p: Path) -> Optional[str]:
    """Stripped file contents, or None when missing/unreadable/empty."""
    try:
        return p.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def ensure_management_token(*, force: bool = False) -> str:
    """Return the management-API bearer key (0600 at <proxy>/management.token), minting on first call."""
    p = _proxy_state_dir() / "management.token"
    if not force and (existing := _read_text_or_none(p)):
        return existing
    token = mint_proxy_token(prefix="arkos-mgmt")
    _write_private_file(p, token.encode("utf-8"))
    return token


def _yaml():
    """PyYAML module or None (it is a Arkos dep, but never a hard requirement here)."""
    try:
        import yaml
        return yaml
    except ImportError:
        return None


def _parse_listen(listen) -> Optional[Tuple[str, int]]:
    """``"host:port"`` -> ``(host, port)``; empty host means loopback."""
    if not isinstance(listen, str) or ":" not in listen:
        return None
    host, _, port_s = listen.rpartition(":")
    try:
        port = int(port_s)
    except ValueError:
        return None
    return (host or "127.0.0.1", port)


def _config_listen(section: str, *keys: str, config_path: Optional[Path] = None) -> Optional[Tuple[str, int]]:
    """``(host, port)`` from the first truthy ``proxy.yaml[section][key]``, or None (also when file/PyYAML is missing)."""
    yaml, data = _yaml(), {}
    if yaml is not None:
        with suppress(OSError, yaml.YAMLError):
            data = yaml.safe_load((config_path or (_proxy_state_dir_ro() / "proxy.yaml")).read_text(encoding="utf-8")) or {}
    block = data.get(section) or {}
    return _parse_listen(next((block[k] for k in keys if block.get(k)), ""))


def _read_management_listen_from_config(config_path: Optional[Path] = None) -> Optional[Tuple[str, int]]:
    return _config_listen("management", "listen", config_path=config_path)


def _probe_target() -> Tuple[str, int]:
    """Configured bind host/port to probe — on Linux the docker bridge, where a loopback connect would report a healthy
    daemon as down.  ``tunnel_listen`` (CONNECT/MITM) falls back to ``http_listen`` for pre-listener-role-split configs."""
    return _config_listen("proxy", "tunnel_listen", "http_listen") or ("127.0.0.1", _DEFAULT_TUNNEL_PORT)


_RELOAD_HTTP_ERRORS = {
    422: "iron-proxy rejected the new config (validation failed; the running ruleset is unchanged): {body}",
    401: "management API rejected our key (401).  The running daemon was started with a different management.token — run `arkos egress restart`.",
}


def reload_proxy() -> bool:
    """``POST /v1/reload`` (validation failures leave the running config untouched); actionable RuntimeError on any failure."""
    if not (pid := _read_pid()) or not _pid_alive(pid):
        raise RuntimeError("iron-proxy is not running — nothing to reload.  Run `arkos egress start`.")
    if (mgmt := _read_management_listen_from_config()) is None:
        raise RuntimeError(
            "The generated proxy.yaml has no management listener (written before reload support).  Re-run `arkos egress setup` and use `arkos egress restart` this one time."
        )
    if not (token := _read_text_or_none(_proxy_state_dir_ro() / "management.token")):
        raise RuntimeError("management.token is missing — re-run `arkos egress setup`, then `arkos egress restart`.")
    host, port = mgmt
    req = urllib.request.Request(f"http://{host}:{port}/v1/reload", method="POST", headers={"Authorization": f"Bearer {token}"}, data=b"")
    try:
        with urllib.request.urlopen(req, timeout=_MGMT_RELOAD_TIMEOUT) as resp:
            if resp.status == 200:
                return True
            raise RuntimeError(f"management API returned unexpected status {resp.status}")
    except urllib.error.HTTPError as exc:
        body = ""
        with suppress(OSError):
            body = exc.read().decode("utf-8", errors="replace")[:500]
        message = _RELOAD_HTTP_ERRORS.get(exc.code, "management reload failed (HTTP {code}): {body}")
        raise RuntimeError(message.format(code=exc.code, body=body)) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(
            f"could not reach the management API at {host}:{port} ({exc}).  If the daemon was started before reload support, run `arkos egress restart` once."
        ) from exc


def _default_http_listen(tunnel_port: int) -> List[str]:
    """Single bind (v0.39 allows one): docker bridge on Linux (what ``host.docker.internal`` resolves to; loopback is
    unreachable from containers), loopback on Docker Desktop (VPNkit).  NEVER 0.0.0.0: a LAN peer with a leaked
    sandbox token could spend the operator's API quota."""
    if platform.system() == "Linux":
        if (bridge_ip := _detect_docker_bridge_ip()) and bridge_ip != "127.0.0.1":
            return [f"{bridge_ip}:{tunnel_port}"]
        logger.warning(
            "No docker bridge (docker0) detected — binding iron-proxy to loopback only.  Docker sandboxes will NOT be able to reach the proxy until it is restarted with docker running."
        )
    return [f"127.0.0.1:{tunnel_port}"]


def _detect_docker_bridge_ip() -> Optional[str]:
    """docker0 IPv4 via ``ip -4 addr show docker0``, or None.  SECURITY: validated through
    :mod:`ipaddress` so a hostile ``ip`` shim can't inject 0.0.0.0/loopback/multicast/link-local/public."""
    try:
        res = _run(["ip", "-4", "-o", "addr", "show", "docker0"], timeout=2, text=True)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (line.split() for line in res.stdout.splitlines()) if res.returncode == 0 else ()
    candidate = next((parts[parts.index("inet") + 1].split("/")[0] for parts in lines if "inet" in parts[:-1]), None)
    try:
        addr = ipaddress.IPv4Address(candidate)
    except (ipaddress.AddressValueError, ValueError):
        return None
    if addr.is_unspecified or addr.is_loopback or addr.is_multicast or addr.is_reserved or addr.is_link_local or addr.is_global:
        logger.warning("Refusing suspicious docker bridge IP %s reported by `ip`; skipping bridge bind.", candidate)
        return None
    return str(addr)


def build_proxy_config(
    *, mappings: List[TokenMapping], ca_cert: Path, ca_key: Path, tunnel_port: int = _DEFAULT_TUNNEL_PORT, audit_log: Optional[Path] = None,
    allowed_hosts: Optional[List[str]] = None, upstream_deny_cidrs: Optional[List[str]] = None, http_listen: Optional[List[str]] = None,
) -> Dict:
    """iron-proxy YAML config dict (v0.39.0 schema).  Real secrets come from iron-proxy's OWN env (``source: {type: env}``);
    the sandbox never sees them.  ``upstream_deny_cidrs=None`` = default SSRF deny list, ``[]`` opts out.
    ``audit_log`` is forward-compat only (v0.39 rejects ``audit_path``)."""
    hosts: List[str] = list(allowed_hosts or _DEFAULT_ALLOWED_HOSTS)
    for h in (h for m in mappings for h in m.upstream_hosts):
        if h not in hosts:
            hosts.append(h)
    deny_cidrs = list(_DEFAULT_UPSTREAM_DENY_CIDRS if upstream_deny_cidrs is None else upstream_deny_cidrs)
    secrets_rules = [{
        "source": {"type": "env", "var": m.real_env_name},
        "replace": {
            "proxy_value": m.proxy_token, "match_headers": list(m.match_headers or ("Authorization",)),
            "match_query": True, "match_body": False, "require": True,
        },
        "rules": [{"host": h} for h in m.upstream_hosts],
    } for m in mappings]
    primary_listen = (list(http_listen) if http_listen else _default_http_listen(tunnel_port) or [f"127.0.0.1:{tunnel_port}"])[0]
    bind_host = primary_listen.rsplit(":", 1)[0] or "127.0.0.1"
    return {
        "dns": {"listen": "127.0.0.1:0", "proxy_ip": "127.0.0.1"},
        "proxy": {
            "tunnel_listen": primary_listen, "http_listen": f"{bind_host}:{tunnel_port + 1}",
            "https_listen": "127.0.0.1:0",
            "max_request_body_bytes": 16 * 1024 * 1024, "max_response_body_bytes": 0,
            "upstream_response_header_timeout": "120s", "upstream_deny_cidrs": deny_cidrs,
        },
        "metrics": {"listen": "127.0.0.1:0"},
        "management": {"listen": f"127.0.0.1:{tunnel_port + _MGMT_PORT_OFFSET}", "api_key_env": _MGMT_API_KEY_ENV},
        "tls": {"ca_cert": str(ca_cert), "ca_key": str(ca_key), "cert_cache_size": 1000, "leaf_cert_expiry_hours": 168},
        "transforms": [{"name": "allowlist", "config": {"domains": hosts}}, {"name": "secrets", "config": {"secrets": secrets_rules}}],
        "log": {"level": "info"},
    }


def _open_private_append(path: Path, *, strict_chmod: bool) -> int:
    """O_APPEND|O_CREAT 0o600 + O_NOFOLLOW (planted symlinks refused); fchmod tightens a pre-existing
    file (failure fatal iff ``strict_chmod``).  Raises OSError; caller owns the fd."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND | _O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        if strict_chmod:
            os.close(fd)
            raise
    return fd


def ensure_audit_log(audit_path: Path) -> None:
    """Pre-create the audit log 0o600 (forward-compat: v0.39 never writes it); RuntimeError on any OSError."""
    try:
        os.close(_open_private_append(audit_path, strict_chmod=True))
    except OSError as exc:
        raise RuntimeError(
            f"Refusing to start: could not pre-create audit log {audit_path} with restrictive permissions ({exc}).  Move or chmod any existing file at that path and retry."
        ) from exc


def _write_state_file_atomic(state: Path, name: str, dump) -> Path:
    """0600 temp file + atomic replace: the file holds proxy tokens; chmod-after-replace would be a world-readable TOCTOU window."""
    tmp_path = state / f".{name}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        dump(f)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, state / name)
    return state / name


def write_proxy_config(config: Dict) -> Path:
    """Serialize the config dict to ``<arkos_home>/proxy/proxy.yaml`` (safe_dump, no Python tags)."""
    if (yaml := _yaml()) is None:
        raise RuntimeError("PyYAML is required to write the iron-proxy config but is not installed.")
    return _write_state_file_atomic(_proxy_state_dir(), "proxy.yaml", lambda f: yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False))


def write_mappings(mappings: List[TokenMapping]) -> Path:
    """Persist sandbox-visible tokens to ``mappings.json`` (read by the Docker backend, not iron-proxy)."""
    payload = {"version": 1, "tokens": [{
        "proxy_token": m.proxy_token, "env_name": m.real_env_name, "upstream_hosts": list(m.upstream_hosts),
        "match_headers": list(m.match_headers), "alias_env_names": list(m.alias_env_names),
    } for m in mappings]}
    return _write_state_file_atomic(_proxy_state_dir(), "mappings.json", lambda f: json.dump(payload, f, indent=2))


def load_mappings() -> List[TokenMapping]:
    """Read mappings.json, if it exists.  Empty list on any error."""
    if not (f := _proxy_state_dir() / "mappings.json").exists():
        return []
    try:
        payload = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read iron-proxy mappings.json: %s", exc)
        return []
    out: List[TokenMapping] = []
    for item in payload.get("tokens", []):
        with suppress(KeyError, TypeError):
            out.append(TokenMapping(item["proxy_token"], item["env_name"], tuple(item.get("upstream_hosts") or ()),
                                    tuple(item.get("match_headers") or ("Authorization",)), tuple(item.get("alias_env_names") or ())))
    return out


def discover_provider_mappings(*, available_env_names: Optional[List[str]] = None) -> List[TokenMapping]:
    """One TokenMapping per known provider whose env var is set (bearer providers first).  Canonical OR any alias
    present -> ONE mapping on the canonical name (the subprocess-env builder mirrors aliases).
    ``available_env_names`` (Bitwarden adapter) overrides the non-empty names in the host env."""
    names = set(available_env_names) if available_env_names is not None else {k for k, v in os.environ.items() if v}
    specs = [(n, h, ("Authorization",), ()) for n, h in _BEARER_PROVIDERS.items()] + [
        (n, tuple(s["hosts"]), tuple(s["match_headers"]), tuple(s.get("aliases") or ())) for n, s in _HEADER_AUTH_PROVIDERS.items()
    ]
    return [
        TokenMapping(mint_proxy_token(prefix=env_name.lower().replace("_api_key", "")), env_name, hosts, headers, aliases)
        for env_name, hosts, headers, aliases in specs
        if env_name in names or any(a in names for a in aliases)
    ]


def discover_uncovered_providers(*, available_env_names: Optional[List[str]] = None) -> List[str]:
    """Env names of recognized providers the proxy can't swap (SigV4 / SDK-minted OAuth)."""
    names = set(available_env_names) if available_env_names is not None else {k for k, v in os.environ.items() if v}
    return [n for n in _NON_BEARER_PROVIDERS if n in names]


def merge_mappings(*, existing: List[TokenMapping], discovered: List[TokenMapping], rotate: bool = False) -> List[TokenMapping]:
    """Existing tokens are preserved (containers baked with them keep working), hosts/headers/aliases refresh
    from ``discovered``; ``rotate=True`` re-mints; undiscovered providers drop."""
    by_name = {} if rotate else {m.real_env_name: m for m in existing}
    return [replace(d, proxy_token=by_name[d.real_env_name].proxy_token) if d.real_env_name in by_name else d for d in discovered]


def _pidfile() -> Path:
    return _proxy_state_dir() / "iron-proxy.pid"


def _read_pid() -> Optional[int]:
    try:
        pid = int(_read_text_or_none(_proxy_state_dir_ro() / "iron-proxy.pid") or "")
    except ValueError:
        return None
    return pid if pid > 0 else None


def _pid_proc_starttime(pid: int) -> Optional[str]:
    """/proc/<pid>/stat starttime (field 22) on Linux, else None — cheap PID-recycling detector."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    fields = text[rparen + 1:].split() if (rparen := text.rfind(")")) >= 0 else []
    return fields[19] if len(fields) > 19 else None


def _persisted_nonce_path() -> Path:
    """On-disk nonce sibling of the pidfile, so stop/status in a later CLI process can still defeat PID recycling."""
    return _proxy_state_dir_ro() / "iron-proxy.nonce"


def _read_persisted_nonce() -> Optional[str]:
    """Nonce from disk, or None if missing/unreadable/empty/not owned by us (callers fall back to argv0
    matching).  O_NOFOLLOW: this read decides whether stop_proxy SIGKILLs a PID."""
    try:
        fd = os.open(str(_persisted_nonce_path()), os.O_RDONLY | _O_NOFOLLOW)
    except OSError:
        return None
    try:
        if not _fd_owned_by_us(fd):
            return None
        return os.read(fd, 256).decode("utf-8", errors="ignore").strip() or None
    finally:
        os.close(fd)


def _pid_alive(pid: int) -> bool:
    """True iff ``pid`` is alive AND an iron-proxy process.  PID-reuse defense, in priority order: nonce in
    /proc/<pid>/environ, argv[0] basename in /proc/<pid>/cmdline, ``ps -o comm=`` basename (a loose
    ``"iron-proxy" in cmdline`` would hit ``tail iron-proxy.log``)."""
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore
        if not psutil.pid_exists(pid):
            return False
    except ImportError:
        if platform.system() != "Windows":
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError, OSError):
                return False
    nonce_candidates = [n for n in dict.fromkeys((_proxy_nonce, _read_persisted_nonce())) if n]
    if nonce_candidates:
        with suppress(OSError):
            env_bytes = Path(f"/proc/{pid}/environ").read_bytes()
            if any(f"{_ARKOS_IRON_PROXY_NONCE_ENV}={n}".encode() in env_bytes for n in nonce_candidates):
                return True
    with suppress(OSError):
        if (cmdline_path := Path(f"/proc/{pid}/cmdline")).exists():
            return os.path.basename(cmdline_path.read_bytes().split(b"\x00")[0].decode("utf-8", errors="ignore")).startswith("iron-proxy")
    with suppress(OSError, subprocess.TimeoutExpired):
        res = _run(["ps", "-p", str(pid), "-o", "comm="], timeout=2, text=True)
        if res.returncode == 0:
            return os.path.basename((res.stdout or "").strip()).startswith("iron-proxy")
    return True


def start_proxy(
    *, binary: Optional[Path] = None, config_path: Optional[Path] = None, extra_env: Optional[Dict[str, str]] = None,
    install_if_missing: bool = True, refresh_secrets_from_bitwarden: bool = False, bitwarden_config: Optional[Dict] = None,
) -> ProxyStatus:
    """Spawn iron-proxy as a managed background subprocess (idempotent if already running).  ``refresh_secrets_from_bitwarden``
    re-fetches secrets from BWS — the ``credential_source: bitwarden`` rotation promise."""
    global _proxy_nonce
    if (existing := _read_pid()) and _pid_alive(existing):
        return get_status()
    if (bin_path := binary or find_iron_proxy(install_if_missing=install_if_missing)) is None:
        raise RuntimeError("iron-proxy binary not available — run `arkos egress install`.")
    if not (cfg := config_path or (_proxy_state_dir() / "proxy.yaml")).exists():
        raise RuntimeError(f"iron-proxy config not found at {cfg}. Run `arkos egress setup` first.")
    env = _build_proxy_subprocess_env(extra_env=extra_env, refresh_from_bitwarden=refresh_secrets_from_bitwarden, bitwarden_config=bitwarden_config)
    if _read_management_listen_from_config(cfg) is not None:
        env[_MGMT_API_KEY_ENV] = ensure_management_token()
    _proxy_nonce = hashlib.sha256(os.urandom(16)).hexdigest()
    env[_ARKOS_IRON_PROXY_NONCE_ENV] = _proxy_nonce
    log_path = _proxy_state_dir() / "iron-proxy.log"
    proc = _spawn_daemon(bin_path, cfg, env, log_path)
    pidfile = _pidfile()
    try:
        _write_pidfile_safely(pidfile, proc.pid)
    except RuntimeError:
        _kill_and_wait(proc, grace_seconds=2)
        raise

    def _abort(msg: str, *, kill: bool) -> RuntimeError:
        tail = _tail_log(log_path, lines=20)
        if kill:
            _kill_and_wait(proc, grace_seconds=2)
        pidfile.unlink(missing_ok=True)
        return RuntimeError(f"{msg}Last log lines:\n{tail}")

    def _interrupt_handler(_signum, _frame):  # pragma: no cover - signal path
        _kill_and_wait(proc, grace_seconds=2)
        pidfile.unlink(missing_ok=True)
        raise KeyboardInterrupt()

    _exited_error = lambda: _abort(f"iron-proxy exited immediately (code {proc.returncode}). ", kill=False)  # noqa: E731
    probe_host, tunnel_port = _probe_target()
    with _interrupt_guard(_interrupt_handler):
        listening = _await_listening(proc, probe_host, tunnel_port, on_exit=_exited_error)
    if proc.poll() is not None:
        raise _exited_error()
    if not listening:
        raise _abort(f"iron-proxy did not bind {probe_host}:{tunnel_port} within {_STARTUP_GRACE_SECONDS}s.  Process was killed.  ", kill=True)
    logger.info("Started iron-proxy pid=%s config=%s", proc.pid, cfg)
    return get_status()


@contextmanager
def _interrupt_guard(handler):
    """Route SIGINT/SIGTERM to ``handler`` for the block (POSIX main thread only); previous handlers restored after."""
    if platform.system() == "Windows" or threading.current_thread() is not threading.main_thread():
        yield
        return
    prev = [(sig, signal.signal(sig, handler)) for sig in (signal.SIGINT, signal.SIGTERM)]
    try:
        yield
    finally:
        for sig, old in prev:
            signal.signal(sig, old)


def _spawn_daemon(bin_path: Path, cfg: Path, env: Dict[str, str], log_path: Path) -> "subprocess.Popen":
    """Popen with stdout/stderr appended to ``log_path`` (0o600 from the first byte, O_NOFOLLOW so a planted
    symlink e.g. to authorized_keys can't receive output, owner-checked).  Our log fd closes after Popen — the child has its dup."""
    try:
        log_fd = _open_private_append(log_path, strict_chmod=False)
    except OSError as exc:
        raise RuntimeError(f"Refusing to write iron-proxy log {log_path}: {exc}.  Remove that path manually and retry.") from exc
    if not _fd_owned_by_us(log_fd):
        uid = os.fstat(log_fd).st_uid
        os.close(log_fd)
        raise RuntimeError(f"iron-proxy log {log_path} has unexpected owner uid={uid}; refusing to write.")
    try:
        return subprocess.Popen(  # noqa: S603
            [str(bin_path), "-config", str(cfg)], env=env, stdin=subprocess.DEVNULL, stdout=log_fd, stderr=subprocess.STDOUT,
            **({} if platform.system() == "Windows" else {"start_new_session": True}),
        )
    except OSError as exc:
        raise RuntimeError(f"failed to spawn iron-proxy: {exc}") from exc
    finally:
        with suppress(OSError):
            os.close(log_fd)


def _await_listening(proc: "subprocess.Popen", host: str, port: int, *, on_exit) -> bool:
    """Poll until ``host:port`` accepts or the grace window lapses (do-while: >=1 check even at 0s); raises ``on_exit()`` if the child dies."""
    deadline = time.time() + _STARTUP_GRACE_SECONDS
    while True:
        if proc.poll() is not None:
            raise on_exit()
        if _port_listening(host, port):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.1)


def _write_pidfile_safely(pidfile: Path, pid: int) -> None:
    """O_EXCL + O_NOFOLLOW + ownership check, then persist the nonce.  An existing pidfile is either a concurrent
    start (fail cleanly) or a stale crash leftover (unlink and retry once)."""
    open_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW
    try:
        fd = os.open(str(pidfile), open_flags, 0o600)
    except FileExistsError:
        if (existing_pid := _read_pid()) and _pid_alive(existing_pid):
            raise RuntimeError(
                f"Another iron-proxy start appears to be in progress (pidfile {pidfile} -> pid {existing_pid}).  Run `arkos egress stop` if that proxy is stuck."
            )
        pidfile.unlink(missing_ok=True)
        fd = os.open(str(pidfile), open_flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"Refusing to write pidfile {pidfile}: {exc}.  Remove that path manually and retry.") from exc
    try:
        if not _fd_owned_by_us(fd):
            raise RuntimeError(f"pidfile {pidfile} has unexpected owner uid={os.fstat(fd).st_uid}")
        os.write(fd, str(pid).encode("utf-8"))
    finally:
        os.close(fd)
    if _proxy_nonce:
        with suppress(OSError):
            _write_private_file(pidfile.with_suffix(".nonce"), _proxy_nonce.encode("utf-8"))


def _kill_and_wait(proc: "subprocess.Popen", *, grace_seconds: int = 2) -> None:
    try:
        proc.terminate()
    except OSError:
        return
    try:
        proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        with suppress(OSError):
            proc.kill()
        with suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=grace_seconds)


def _build_proxy_subprocess_env(
    *, extra_env: Optional[Dict[str, str]] = None, refresh_from_bitwarden: bool = False, bitwarden_config: Optional[Dict] = None,
) -> Dict[str, str]:
    """Allowlisted infra vars + the secrets named in mappings.  With ``refresh_from_bitwarden`` and a populated
    ``bitwarden_config`` secrets come from BWS (the rotation guarantee); without ``allow_env_fallback`` any BWS
    shortfall fails closed instead of keeping stale host-env values."""
    env, parent = _allowlisted_env(), os.environ
    mappings = load_mappings()
    needed = {m.real_env_name for m in mappings}
    alias_sources = {m.real_env_name: m.alias_env_names for m in mappings if m.alias_env_names}
    for name in needed:
        if (source := name if name in parent else next((a for a in alias_sources.get(name, ()) if parent.get(a)), None)) is not None:
            env[name] = parent[source]
    if refresh_from_bitwarden and bitwarden_config:
        _refresh_secrets_from_bitwarden(env, needed, bitwarden_config, bool(bitwarden_config.get("allow_env_fallback")))
    if extra_env:
        env.update(extra_env)
    for name in _PROXY_SUBPROCESS_ENV_STRIP:
        env.pop(name, None)
    env.setdefault("NO_COLOR", "1")
    return env


def _bitwarden_shortfall(allow_env_fallback: bool, error: str, warning: str, *args, cause: Optional[BaseException] = None) -> None:
    """Raise ``error`` (chained to ``cause`` when given) unless the operator opted into the legacy host-env fallback (then log ``warning``)."""
    if not allow_env_fallback:
        if cause is not None:
            raise RuntimeError(error) from cause
        raise RuntimeError(error)
    logger.warning(warning, *args)


def _refresh_secrets_from_bitwarden(env: Dict[str, str], needed: set, bitwarden_config: Dict, allow_env_fallback: bool) -> None:
    """Overwrite ``env[needed]`` with fresh (uncached) BWS values; only mapped names are injected so unrelated BWS secrets never leak."""
    try:
        from agent.secret_sources import bitwarden as bw
        access_token = os.environ.get(bitwarden_config.get("access_token_env", "BWS_ACCESS_TOKEN"), "").strip()
        project_id = bitwarden_config.get("project_id", "")
        if not (access_token and project_id):
            _bitwarden_shortfall(
                allow_env_fallback,
                "credential_source=bitwarden but the access-token env or project_id is empty.  Either set both, switch to "
                "credential_source: env, or set `proxy.allow_env_fallback: true` to opt into the legacy fallback behaviour.",
                "credential_source=bitwarden but access-token env or project_id is empty — proxy will fall back to parent env (allow_env_fallback=true).",
            )
            return
        secrets, warnings = bw.fetch_bitwarden_secrets(access_token=access_token, project_id=project_id, cache_ttl_seconds=0, use_cache=False)
    except ImportError as exc:
        _bitwarden_shortfall(
            allow_env_fallback,
            "Bitwarden refresh module unavailable at proxy start (credential_source=bitwarden with "
            "proxy.allow_env_fallback: false).  Either fix the import, switch to credential_source: env, or set "
            "`proxy.allow_env_fallback: true` to opt into the legacy fallback behaviour.",
            "Bitwarden refresh module unavailable at proxy start, falling back to parent env (allow_env_fallback=true): %s", exc, cause=exc,
        )
        return
    missing = sorted(needed - set(secrets))
    env.update((n, secrets[n]) for n in needed if n in secrets)
    if missing:
        _bitwarden_shortfall(
            allow_env_fallback,
            f"Bitwarden refresh did not return secrets for {missing}.  Either add the secrets to your BWS project, switch to "
            f"credential_source: env via `arkos egress setup --no-bitwarden`, or set `proxy.allow_env_fallback: true` in "
            f"config.yaml to opt into the legacy host-env fallback.",
            "Bitwarden refresh did not return secrets for %s — falling back to host env for those names (allow_env_fallback=true).", missing,
        )
    if warnings:
        logger.warning("Bitwarden refresh produced %d warning(s); run `arkos secrets bitwarden status` for detail.", len(warnings))


def _forget_daemon() -> None:
    global _proxy_nonce
    _pidfile().unlink(missing_ok=True)
    with suppress(OSError):
        _persisted_nonce_path().unlink()
    _proxy_nonce = None


def stop_proxy() -> bool:
    """Returns True if it was running."""
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        _forget_daemon()
        return False
    starttime_before = _pid_proc_starttime(pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _forget_daemon()
        return False
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    else:
        starttime_after = _pid_proc_starttime(pid)
        if (starttime_before is not None and starttime_after is not None and starttime_before != starttime_after) or not _pid_alive(pid):
            logger.warning("iron-proxy pid=%s appears recycled before SIGKILL; not killing.", pid)
        else:
            with suppress(ProcessLookupError):
                os.kill(pid, _KILL_SIGNAL)
    _forget_daemon()
    logger.info("Stopped iron-proxy pid=%s", pid)
    return True


def get_status() -> ProxyStatus:
    """Snapshot the proxy state without side effects (called per Docker container create)."""
    status = ProxyStatus()
    probe_host, status.tunnel_port = _probe_target()
    if binary := find_iron_proxy(install_if_missing=False):
        status.binary_path, status.binary_version = binary, iron_proxy_version(binary)
    state = _proxy_state_dir_ro()
    cfg, ca = state / "proxy.yaml", state / "ca.crt"
    status.config_path, status.ca_cert_path = (cfg if cfg.exists() else None), (ca if ca.exists() else None)
    if (pid := _read_pid()) and _pid_alive(pid):
        status.pid, status.listening = pid, _port_listening(probe_host, status.tunnel_port)
    return status


def _port_listening(host: str, port: int) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _tail_log(path: Path, *, lines: int = 20) -> str:
    if not path.exists():
        return "(no log file)"
    try:
        return "\n".join(path.read_bytes()[-8192:].decode("utf-8", errors="replace").splitlines()[-lines:])
    except OSError as exc:
        return f"(could not read log: {exc})"


def _reset_for_tests() -> None:
    global _proxy_nonce
    _VERSION_CACHE.clear()
    _proxy_nonce = None


__all__ = [
    "ProxyStatus", "TokenMapping", "build_proxy_config", "discover_provider_mappings",
    "discover_uncovered_providers", "ensure_audit_log", "ensure_ca_cert", "ensure_management_token",
    "find_iron_proxy", "get_status", "install_iron_proxy", "iron_proxy_version", "load_mappings",
    "merge_mappings", "mint_proxy_token", "reload_proxy", "start_proxy", "stop_proxy",
    "write_mappings", "write_proxy_config",
]


import stat  # noqa: F401,E402
