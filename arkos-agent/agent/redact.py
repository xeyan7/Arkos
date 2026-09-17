"""Regex-based secret redaction for logs and tool output.

Short tokens (< 18 chars) are fully masked; longer ones keep the first 6 and
last 4 characters for debuggability.
"""

import logging
import os
import re
import shlex
import threading
from urllib.parse import unquote_plus

from agent.file_safety import _BLOCKED_PROJECT_ENV_BASENAMES as _ENV_FILE_BASENAMES

logger = logging.getLogger(__name__)

_SENSITIVE_QUERY_PARAMS = frozenset({
    "access_token", "refresh_token", "id_token", "token", "api_key", "apikey",
    "client_secret", "password", "auth", "jwt", "session", "secret", "key",
    "code", "signature", "x-amz-signature",
})

_REDACT_ENABLED = os.getenv("ARKOS_REDACT_SECRETS", "true").lower() in {"1", "true", "yes", "on"}

_PREFIX_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{10,}",
    r"ghp_[A-Za-z0-9]{10,}",
    r"github_pat_[A-Za-z0-9_]{10,}",
    r"gho_[A-Za-z0-9]{10,}",
    r"ghu_[A-Za-z0-9]{10,}",
    r"ghs_[A-Za-z0-9]{10,}",
    r"ghr_[A-Za-z0-9]{10,}",
    r"xapp-\d+-[A-Za-z0-9-]{10,}",
    r"xox[baprs]-[A-Za-z0-9-]{10,}",
    r"AIza[A-Za-z0-9_-]{30,}",
    r"pplx-[A-Za-z0-9]{10,}",
    r"fal_[A-Za-z0-9_-]{10,}",
    r"fc-[A-Za-z0-9]{10,}",
    r"bb_live_[A-Za-z0-9_-]{10,}",
    r"gAAAA[A-Za-z0-9_=-]{20,}",
    r"AKIA[A-Z0-9]{16}",
    r"sk_live_[A-Za-z0-9]{10,}",
    r"sk_test_[A-Za-z0-9]{10,}",
    r"rk_live_[A-Za-z0-9]{10,}",
    r"SG\.[A-Za-z0-9_-]{10,}",
    r"hf_[A-Za-z0-9]{10,}",
    r"r8_[A-Za-z0-9]{10,}",
    r"npm_[A-Za-z0-9]{10,}",
    r"pypi-[A-Za-z0-9_-]{10,}",
    r"dop_v1_[A-Za-z0-9]{10,}",
    r"doo_v1_[A-Za-z0-9]{10,}",
    r"am_[A-Za-z0-9_-]{10,}",
    r"sk_[A-Za-z0-9_]{10,}",
    r"tvly-[A-Za-z0-9]{10,}",
    r"exa_[A-Za-z0-9]{10,}",
    r"gsk_[A-Za-z0-9]{10,}",
    r"syt_[A-Za-z0-9]{10,}",
    r"retaindb_[A-Za-z0-9]{10,}",
    r"hsk-[A-Za-z0-9]{10,}",
    r"mem0_[A-Za-z0-9]{10,}",
    r"brv_[A-Za-z0-9]{10,}",
    r"xai-[A-Za-z0-9]{30,}",
    r"ntn_[A-Za-z0-9]{10,}",
    r"fw-[A-Za-z0-9]{30,}",
    r"fw_[A-Za-z0-9]{30,}",
    r"fpk_[A-Za-z0-9]{30,}",
    r"glpat-[A-Za-z0-9_\-]{10,}",
    r"gloas-[A-Za-z0-9_\-]{10,}",
    r"gldt-[A-Za-z0-9_\-]{10,}",
    r"glrt-[A-Za-z0-9_.\-]{10,}",
    r"glrtr-[A-Za-z0-9_.\-]{10,}",
    r"glcbt-[A-Za-z0-9_\-]{10,}",
    r"glptt-[A-Za-z0-9_\-]{10,}",
    r"glft-[A-Za-z0-9_\-]{10,}",
    r"glimt-[A-Za-z0-9_\-]{10,}",
    r"glagent-[A-Za-z0-9_\-]{10,}",
    r"glsoat-[A-Za-z0-9_\-]{10,}",
    r"glffct-[A-Za-z0-9_\-]{10,}",
    r"glwt-[A-Za-z0-9_\-]{10,}",
    r"GR1348941[A-Za-z0-9_\-]{10,}",
    r"pk-lf-[A-Za-z0-9\-]{8,}",
]

_SECRET_ENV_NAMES = r"(?:API_?KEY|KEY|TOKEN|SECRET|PASSWORD|PASSWD|PASS|PW|CREDENTIAL|AUTH)"
_ENV_ASSIGN_RE = re.compile(rf"([A-Z0-9_]{{0,50}}{_SECRET_ENV_NAMES}[A-Z0-9_]{{0,50}})\s*=\s*(['\"]?)(\S+)\2")
_ENV_ASSIGN_LOWER_RE = re.compile(
    rf"(?<![a-z0-9_])([a-z0-9_]+(?:_|^)(?:key|pass|pw|token|secret|password|passwd|credential|auth)(?=[^a-z0-9_]|$))\s*=\s*(['\"]?)(\S+)\2",
    re.IGNORECASE,
)

_SECRET_CFG_NAMES = r"(?:api[ _.\-]?key|token|secret|passwd|password|credential|auth)"
_CFG_VALUE = r"(['\"]?)([^\s&]+?)\2(?=[\s&]|$)"
_CFG_SECRET_WORD_RE = re.compile(_SECRET_CFG_NAMES, re.IGNORECASE)

_ENV_LOOKUP_VALUE_RE = re.compile(r"^(?:os\.(?:getenv|environ)|process\.env|\$ENV\{)")
_CFG_DOTTED_RE = re.compile(
    rf"(?<![A-Za-z0-9_.\-])"
    rf"([A-Za-z0-9_\-]++\.[A-Za-z0-9_.\-]*{_SECRET_CFG_NAMES}[A-Za-z0-9_.\-]*+"
    rf"|[A-Za-z0-9_.\-]*{_SECRET_CFG_NAMES}[A-Za-z0-9_.\-]*\.[A-Za-z0-9_.\-]++)"
    rf"={_CFG_VALUE}",
    re.IGNORECASE,
)
_CFG_ANCHORED_RE = re.compile(
    rf"(^[ \t]*(?:export[ \t]+)?[A-Za-z0-9_\-]*{_SECRET_CFG_NAMES}[A-Za-z0-9_\-]*)={_CFG_VALUE}",
    re.IGNORECASE | re.MULTILINE,
)

_YAML_CFG_NAMES = r"(?:api[ _.\-]?key|token|secret|passwd|password|credential)"
_YAML_ASSIGN_RE = re.compile(
    rf"(^[ \t]*+[A-Za-z0-9_.\-]*{_YAML_CFG_NAMES}[A-Za-z0-9_.\-]*+)(:[ \t]*+)(?!['\"])([^\s&]++)",
    re.IGNORECASE | re.MULTILINE,
)

_KEY_KEYWORD_RE = re.compile(
    r"(?:api|auth|access|refresh|session|secret)[ _.\\-]?(?:key|token)"
    r"|token|secret|passwd|password|pass|pw|credential|auth|key",
    re.IGNORECASE,
)

_STRONG_KEY_KEYWORD_RE = re.compile(
    r"(?:api|auth|access|refresh|session|id|bearer)[ _.\\-]?(?:key|token)"
    r"|key[ _.\\-]?material|secret|passwd|password|pass|pw|credential|auth|bearer",
    re.IGNORECASE,
)


def _is_word_start(s: str, i: int) -> bool:
    """True if position ``i`` in ``s`` begins a word (edge, non-letter before, camelCase/acronym boundary)."""
    if i == 0:
        return True
    prev, cur = s[i - 1], s[i]
    if not prev.isalpha() or (cur.isupper() and prev.islower()):
        return True
    return cur.isupper() and prev.isupper() and i + 1 < len(s) and s[i + 1].islower()


def _is_word_end(s: str, j: int, *, allow_plural: bool = True) -> bool:
    """True if position ``j`` (exclusive end) in ``s`` ends a word; one trailing ``s`` is absorbed."""
    if j >= len(s):
        return True
    cur = s[j]
    if not cur.isalpha() or (cur.isupper() and s[j - 1].islower()):
        return True
    return allow_plural and cur in "sS" and _is_word_end(s, j + 1, allow_plural=False)


def _has_word_bounded_keyword(key: str, keyword_re: "re.Pattern[str]") -> bool:
    """True if ``keyword_re`` matches ``key`` at a word boundary (see _KEY_KEYWORD_RE)."""
    return any(_is_word_start(key, m.start()) and _is_word_end(key, m.end()) for m in keyword_re.finditer(key))


def _key_has_secret_keyword(key: str) -> bool:
    """Post-match key validator: ``API_KEY``/``DB_PW`` count, ``KEYBOARD``/``secretary`` do not."""
    return _has_word_bounded_keyword(key, _KEY_KEYWORD_RE)


def _looks_like_opaque_credential(value: str) -> bool:
    """Credential-like shape test for ambiguous ``token``/``key`` values, so short
    technical scalars (``CPU``, ``local``) are not masked merely for their key name."""
    if value == "***" or value.startswith("«redacted:"):
        return True
    if len(value) >= 16 and re.fullmatch(r"[A-Fa-f0-9]+", value):
        return True
    if len(value) >= 20 and re.fullmatch(r"[A-Za-z0-9_./+=-]+", value):
        return True
    if len(value) < 12:
        return False
    return sum(bool(re.search(p, value)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]")) >= 2


def _should_redact_assignment(key: str, value: str, *, check_keyword: bool) -> bool:
    """Shared gate for the ENV / JSON / YAML assignment passes: skip programmatic env
    lookups used as values, optionally require a word-bounded keyword in the key,
    then redact when the key is unambiguously credential-bearing or the value looks opaque."""
    if _ENV_LOOKUP_VALUE_RE.match(value):
        return False
    if check_keyword and not _key_has_secret_keyword(key):
        return False
    return (_has_word_bounded_keyword(key, _STRONG_KEY_KEYWORD_RE)
            or _looks_like_opaque_credential(value))


_JSON_KEY_NAMES = r"(?:api_?[Kk]ey|token|secret|password|access_token|refresh_token|auth_token|bearer|secret_value|raw_secret|secret_input|key_material)"
_JSON_FIELD_RE = re.compile(rf'("{_JSON_KEY_NAMES}")\s*:\s*"([^"]+)"', re.IGNORECASE)

_AUTH_HEADER_RE = re.compile(r"((?:Proxy-)?Authorization:\s*)([A-Za-z][\w.+-]*\s+)?([^\s\"']+)", re.IGNORECASE)

_SECRET_HEADER_NAMES = r"(?:x-api-key|x-goog-api-key|api-key|apikey|x-api-token|x-auth-token|x-access-token)"
_SECRET_HEADER_RE = re.compile(rf"({_SECRET_HEADER_NAMES}\s*:\s*)(\S+)", re.IGNORECASE)

_TELEGRAM_RE = re.compile(r"(bot)?(\d{8,}):([-A-Za-z0-9_]{30,})")

_PRIVATE_KEY_RE = re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----")

_DB_CONNSTR_RE = re.compile(
    r"((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:\s]+:)([^@\s]+)(@)",
    re.IGNORECASE,
)

_URL_BARE_TOKEN_RE = re.compile(
    r"((?:https?|wss?|git|ssh|ftp|ftps|sftp)://)"
    r"([^\s:@/]{8,})"
    r"(@[^\s]+)",
    re.IGNORECASE,
)

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_=-]{4,}){0,2}")

_SIGNAL_PHONE_RE = re.compile(r"(\+[1-9]\d{6,14})(?![A-Za-z0-9])")

_URL_WITH_QUERY_RE = re.compile(r"(https?|wss?|ftp)://([^\s/?#]+)([^\s?#]*)\?([^\s#]+)(#\S*)?")
_URL_USERINFO_RE = re.compile(r"(https?|wss?|ftp)://([^/\s:@]+):([^/\s@]+)@")

_STRICT_URL_PARAM_RE = re.compile(r"([?#&;])([A-Za-z0-9_.~+%\-]+)=([^#&;\s\"'<>]*)")

_STRICT_URL_USERINFO_RE = re.compile(r"(//)([^/\s?#@]+)@")

_FORM_BODY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*=[^&\s]*(?:&[A-Za-z_][A-Za-z0-9_.-]*=[^&\s]*)+$")

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f\u200b-\u200f\u2028-\u202f\u2060\ufeff]")

_TOKEN_BODY_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.")


def _compile_prefix_matcher(patterns: list) -> "re.Pattern[str]":
    return re.compile(r"(?<![A-Za-z0-9_-])(" + "|".join(patterns) + r")(?![A-Za-z0-9_-])")


_PREFIX_RE = _compile_prefix_matcher(_PREFIX_PATTERNS)


def _mask_control_split_tokens(text: str, mask_fn) -> str:
    """Mask tokens whose body is split by control/zero-width characters.

    Match on a control-stripped copy, then mask the corresponding span in the
    ORIGINAL — only when that span holds solely token-body and control chars, so
    a match can never cross into another line's unrelated text.

    A credential like ``sk-abc\\x1bdef456…`` or ``ghp_abc\\n123def…`` has its token body interrupted, so the
    contiguous _PREFIX_RE cannot match it and the secret leaks verbatim. ``EXA_API_KEY=*** is
    rejected).
    """
    stripped = _CONTROL_CHARS_RE.sub("", text)
    if stripped == text:
        return text
    orig_idx = [i for i, c in enumerate(text) if not _CONTROL_CHARS_RE.match(c)]
    out, matches = list(text), []
    for m in _PREFIX_RE.finditer(stripped):
        start_orig = orig_idx[m.start(1)]
        end_orig = orig_idx[m.end(1) - 1] + 1
        span = text[start_orig:end_orig]
        if ("\n" in span or "\r" in span) and _PREFIX_RE.search(span):
            continue
        if (all(c in _TOKEN_BODY_CHARS or _CONTROL_CHARS_RE.match(c) for c in span)
                and (end_orig >= len(text) or text[end_orig] != "=")):
            matches.append((start_orig, end_orig, mask_fn(m.group(1))))
    for start_orig, end_orig, replacement in reversed(matches):
        out[start_orig:end_orig] = list(replacement)
    return "".join(out)


_DISPLAY_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f\x80-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u2064]")


def mask_secret(value: str, *, head: int = 4, tail: int = 4, floor: int = 12,
                placeholder: str = "***", empty: str = "") -> str:
    """Mask a secret for display (``arkos config`` / ``status`` / ``dump``):
    ``sk-p...7890``; shorter than ``floor`` (after control-byte stripping) →
    ``placeholder``; falsy → ``empty``."""
    value = _DISPLAY_CONTROL_RE.sub("", value) if value else value
    if not value:
        return empty
    return placeholder if len(value) < floor else f"{value[:head]}...{value[-tail:]}"


def _mask_token(token: str) -> str:
    """Mask a log token — 18-char floor, preserves 6 prefix / 4 suffix; empty → ``***``."""
    if not token:
        return "***"
    return mask_secret(token, head=6, tail=4, floor=18)


def _redact_query_string(query: str) -> str:
    """Replace values of sensitive ``k=v&k=v`` params with ``***``; others pass through."""
    if not query:
        return query
    return "&".join(
        f"{key}=***" if sep and key.lower() in _SENSITIVE_QUERY_PARAMS else pair
        for pair in query.split("&") for key, sep, _ in (pair.partition("="),)
    )


def _canonical_url_param_name(name: str) -> str:
    """Decode a URL parameter name (up to 3 unquote rounds) for case-insensitive matching."""
    decoded = name
    for _ in range(3):
        next_value = unquote_plus(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded.casefold().replace("-", "_")


def _redact_strict_url_credentials(text: str) -> str:
    """Strict egress-boundary redaction of URL credentials (absolute, relative and
    network references); preserves keys, separators, public params, hosts, paths."""
    text = _STRICT_URL_PARAM_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}=***"
        if _canonical_url_param_name(m.group(2)) in _SENSITIVE_QUERY_PARAMS else m.group(0), text)
    return _STRICT_URL_USERINFO_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2).partition(':')[0]}:***@" if ":" in m.group(2) else f"{m.group(1)}***@",
        text)


def redact_cdp_url(value: object) -> str:
    """Mask secrets in a CDP/browser endpoint URL before it is logged.

    Unlike ``redact_sensitive_text`` (which passes web-URL query params and
    ``user:pass@`` through for OAuth callbacks / magic links), CDP discovery
    tokens are pure credentials, so this opts INTO both URL redactors.
    """
    text = redact_sensitive_text("" if value is None else str(value))
    if not text:
        return text
    text = _URL_WITH_QUERY_RE.sub(
        lambda m: f"{m.group(1)}://{m.group(2)}{m.group(3)}?{_redact_query_string(m.group(4))}{m.group(5) or ''}",
        text,
    )
    return _URL_USERINFO_RE.sub(lambda m: f"{m.group(1)}://{m.group(2)}:***@", text)


def _redact_form_body(text: str) -> str:
    """Redact sensitive values when the ENTIRE text is a clean ``k=v&k=v`` body."""
    if not text or "\n" in text or "&" not in text or not _FORM_BODY_RE.match(text.strip()):
        return text
    return _redact_query_string(text.strip())


def _mask_token_nonreusable(token: str) -> str:
    """Redact a prefix-matched credential to a NON-REUSABLE sentinel: no head/tail
    chars (an agent once wrote a truncated-looking mask back into a config file),
    only the vendor prefix label so the credential KIND stays visible.

    * cannot be mistaken for a usable-but-truncated key, so an agent that reads it from a config file and
    writes it back does NOT corrupt the stored credential into a dead 13-char string; and *
    still does not leak the secret material (no head/tail chars).
    """
    label = next((sub for sub in _PREFIX_SUBSTRINGS if token.startswith(sub)), "") if token else ""
    return f"«redacted:{label}…»" if label else "«redacted-secret»"


def _assignment_sub(render, *, check_keyword: bool):
    """re.sub callback: keep the match unless the key/value pair (groups[0], groups[-1]) needs redaction."""
    def _sub(m):
        groups = m.groups()
        if not _should_redact_assignment(groups[0], groups[-1], check_keyword=check_keyword):
            return m.group(0)
        return render(groups)
    return _sub


def _redact_assignments(text: str) -> str:
    """ENV / config / JSON / YAML assignment passes (skipped for code files). Passes
    that would match ``token=``/``key=`` URL params skip ``://`` text (web-URL query
    params are intentionally passed through, see redact_sensitive_text)."""
    if "=" in text:
        _redact_env = _assignment_sub(lambda g: f"{g[0]}={g[1]}{_mask_token(g[2])}{g[1]}", check_keyword=True)
        text = _ENV_ASSIGN_RE.sub(_redact_env, text)
        if "://" not in text:
            text = _ENV_ASSIGN_LOWER_RE.sub(_redact_env, text)
        if "://" not in text and _CFG_SECRET_WORD_RE.search(text):
            text = _CFG_DOTTED_RE.sub(_redact_env, text)
            text = _CFG_ANCHORED_RE.sub(_redact_env, text)

    if ":" in text and '"' in text:
        text = _JSON_FIELD_RE.sub(
            _assignment_sub(lambda g: f'{g[0]}: "{_mask_token(g[1])}"', check_keyword=False), text)

    if ":" in text and "://" not in text:
        text = _YAML_ASSIGN_RE.sub(
            _assignment_sub(lambda g: f"{g[0]}{g[1]}{_mask_token(g[2])}", check_keyword=True), text)
    return text


def _redact_url_credentials(text: str, code_file: bool) -> str:
    """DB connection-string passwords and bare-token URL userinfo (``://`` text only)."""
    def _redact_db(m):
        pw = m.group(2)
        if code_file and pw.startswith("{") and pw.endswith("}"):
            return m.group(0)
        return f"{m.group(1)}***{m.group(3)}"
    text = _DB_CONNSTR_RE.sub(_redact_db, text)
    return _URL_BARE_TOKEN_RE.sub(lambda m: f"{m.group(1)}{_mask_token(m.group(2))}{m.group(3)}", text)


def _redact_phone(m):
    phone = m.group(1)
    keep = 2 if len(phone) <= 8 else 4
    return phone[:keep] + "****" + phone[-keep:]


def redact_sensitive_text(text: str, *, force: bool = False, code_file: bool = False,
                          file_read: bool = False, redact_url_credentials: bool = False) -> str:
    """Apply all redaction patterns to a block of text.

    Safe on any string. Enabled by default (``security.redact_secrets: false``
    disables); ``force=True`` is for safety boundaries that must never return
    raw secrets regardless.

    ``redact_url_credentials=True``: also redact credential-named query params
    and ``user:pass@`` userinfo — off by default because OAuth-callback /
    magic-link / pre-signed URLs must survive ordinary tool flows unchanged.
    ``code_file=True``: skip the ENV/JSON assignment passes for known source
    code (``MAX_TOKENS=***``, ``"apiKey": "test"`` fixtures). ``file_read=True``
    (implies code_file): prefix-matched credentials become a non-reusable
    sentinel (``«redacted:ghp_…»``) instead of a head/tail mask an agent could
    write back into config.yaml as a dead credential.

    Every regex sits behind a cheap substring gate that its pattern requires,
    so the gates are never false-negative.

    Set file_read=True for file *content* returned to the agent (read_file / search_files / cat). The old
    mask looked like a real-but-truncated key, so an agent reading it from config.yaml and writing it back
    silently corrupted the stored credential into a dead 13-char value → 401. The sentinel is
    syntactically invalid as a token, so it can't be mistaken for a usable key or written back as one.
    """
    if text is None:
        return None
    text = text if isinstance(text, str) else str(text)
    if not text or not (force or _REDACT_ENABLED):
        return text
    code_file = code_file or file_read

    if _has_known_prefix_substring(text):
        _prefix_sub = _mask_token_nonreusable if file_read else _mask_token
        text = _mask_control_split_tokens(text, _prefix_sub)
        text = _PREFIX_RE.sub(lambda m: _prefix_sub(m.group(1)), text)

    if not code_file:
        text = _redact_assignments(text)

    if "uthorization" in text or "UTHORIZATION" in text:
        text = _AUTH_HEADER_RE.sub(lambda m: m.group(1) + (m.group(2) or "") + _mask_token(m.group(3)), text)

    if ":" in text:
        text = _SECRET_HEADER_RE.sub(lambda m: m.group(1) + _mask_token(m.group(2)), text)
        text = _TELEGRAM_RE.sub(lambda m: f"{m.group(1) or ''}{m.group(2)}:***", text)

    if "BEGIN" in text and "-----" in text:
        text = _PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", text)

    if "://" in text:
        text = _redact_url_credentials(text, code_file)

    if "eyJ" in text:
        text = _JWT_RE.sub(lambda m: _mask_token(m.group(0)), text)

    if redact_url_credentials:
        text = _redact_strict_url_credentials(text)

    if "&" in text and "=" in text:
        text = _redact_form_body(text)

    if "+" in text:
        text = _SIGNAL_PHONE_RE.sub(_redact_phone, text)

    return text


_ENV_DUMP_COMMANDS = frozenset({"env", "printenv", "set", "export", "declare"})

_FILE_READ_COMMANDS = frozenset({
    "cat", "head", "tail", "type", "bat", "less", "more", "nl",
    "zcat", "tac", "view", "batcat",
})


def _command_segments(command: str) -> list[str]:
    """Pipeline/sequence segments of a shell command, stripped, empties dropped."""
    return [seg.strip() for seg in re.split(r"[|;&]+", command) if seg.strip()]


def _command_reads_env_file(command: str | None) -> bool:
    """True if ``command`` reads a ``.env``-style file (by basename) to stdout.
    Defense-in-depth, not a boundary: indirect reads (``sudo cat .env``, ``$(cat
    .env)``, ``sed``/``awk``) are not detected, matching ``is_env_dump_command``."""
    if not command:
        return False
    for seg in _command_segments(command):
        tokens = seg.split()
        if not tokens or tokens[0] not in _FILE_READ_COMMANDS:
            continue
        for arg in tokens[1:]:
            if arg.startswith("-"):
                continue
            basename = arg.strip("\"'").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if basename.lower() in _ENV_FILE_BASENAMES:
                return True
    return False


def is_env_dump_command(command: str | None) -> bool:
    """True if any pipeline/sequence segment starts with an _ENV_DUMP_COMMANDS
    token. Conservative: unrecognized → False (callers fall back to code_file=True)."""
    if not command or not isinstance(command, str):
        return False
    for seg in _command_segments(command):
        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()
        if tokens and tokens[0] in _ENV_DUMP_COMMANDS:
            return True
    return False


def redact_terminal_output(output: str, command: str | None = None, *, force: bool = False) -> str:
    """Single redaction policy for ALL terminal-output surfaces: the ENV-assignment
    pass runs only when ``command`` is an env dump or reads a ``.env`` file
    (otherwise code_file=True avoids false positives on source/config dumps)."""
    if not output:
        return output
    code_file = not (is_env_dump_command(command) or _command_reads_env_file(command))
    return redact_sensitive_text(output, force=force, code_file=code_file)



def _extract_literal_prefix(pattern: str) -> str:
    """Leading literal chars of a regex (up to the first metacharacter)."""
    meta = "[(\\.?*+|{^$"
    for i, ch in enumerate(pattern):
        if ch in meta:
            return pattern[:i]
    return pattern


def _skip_char_class(pattern: str, i: int) -> int:
    """Given ``pattern[i] == "["``, return the index just past the closing ``]``."""
    i += 2 if pattern[i + 1:i + 2] == "]" else 1
    while i < len(pattern) and pattern[i] != "]":
        i += 2 if pattern[i] == "\\" else 1
    return i


def _unbounded_quantifier_follows(pattern: str, j: int) -> bool:
    """True if an open-ended quantifier (``*``, ``+``, ``{m,}``) starts at ``pattern[j]``."""
    if j >= len(pattern):
        return False
    if pattern[j] in "*+":
        return True
    if pattern[j] == "{":
        k = pattern.find("}", j)
        body = pattern[j + 1:k] if k != -1 else ""
        return body[:-1].isdigit() and body.endswith(",")
    return False


def _pattern_structure(pattern: str) -> tuple[bool, bool]:
    """One scan → ``(has_top_level_alternation, has_nested_unbounded_repeat)``.

    Top-level ``|`` defeats the literal-prefix guarantee (in ``ab|.*`` the prefix
    binds only the first branch; ``ab(?:x|y)`` is fine). An unbounded quantifier
    on a group containing one (``(a+)+``, ``(a{2,})+``) is the canonical ReDoS
    shape. Structural only; overlapping branches (``(a|aa)+``) are not detected.
    """
    top_level_alt = nested = False
    contains_unbounded = [False]
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            i = _skip_char_class(pattern, i)
        elif ch == "(":
            contains_unbounded.append(False)
        elif ch == ")":
            inner = contains_unbounded.pop() if len(contains_unbounded) > 1 else False
            if inner and _unbounded_quantifier_follows(pattern, i + 1):
                nested = True
            contains_unbounded[-1] = contains_unbounded[-1] or inner
        elif ch == "|" and len(contains_unbounded) == 1:
            top_level_alt = True
        elif _unbounded_quantifier_follows(pattern, i):
            contains_unbounded[-1] = True
            if ch == "{":
                i = pattern.find("}", i)
        i += 1
    return top_level_alt, nested


def _has_top_level_alternation(pattern: str) -> bool:
    return _pattern_structure(pattern)[0]


def _has_nested_unbounded_repeat(pattern: str) -> bool:
    return _pattern_structure(pattern)[1]


_PREFIX_SUBSTRINGS = tuple(_extract_literal_prefix(p) for p in _PREFIX_PATTERNS)


def _has_known_prefix_substring(text: str) -> bool:
    """Cheap pre-check before the expensive ``_PREFIX_RE``."""
    return any(p in text for p in _PREFIX_SUBSTRINGS)


_PLUGIN_PREFIX_PATTERNS: dict = {}
_registry_lock = threading.Lock()


def _plugin_patterns() -> list:
    """All plugin-registered patterns in registration order."""
    return [p for patterns in _PLUGIN_PREFIX_PATTERNS.values() for p in patterns]


def _rebuild_prefix_matcher() -> None:
    """Recompile the prefix alternation and pre-screen substrings; callers read the
    module globals at call time, so the swap propagates immediately."""
    global _PREFIX_RE, _PREFIX_SUBSTRINGS
    combined = _PREFIX_PATTERNS + _plugin_patterns()
    _PREFIX_RE = _compile_prefix_matcher(combined)
    _PREFIX_SUBSTRINGS = tuple(_extract_literal_prefix(p) for p in combined)


_PATTERN_REJECT_RULES = (
    (_has_top_level_alternation,
     "%s: skipping redaction pattern %r — top-level alternation escapes the literal-prefix "
     "guarantee (in 'ab|.*' the prefix binds only the first branch); wrap alternation in "
     "a group after the prefix, e.g. 'ab(?:x|y)'"),
    (_has_nested_unbounded_repeat,
     "%s: skipping redaction pattern %r — nested unbounded quantifiers (e.g. '(a+)+') can "
     "backtrack catastrophically, and registered patterns run on every log line and tool output"),
    (lambda pattern: len(_extract_literal_prefix(pattern)) < 2,
     "%s: skipping redaction pattern %r — must start with at least 2 literal characters "
     "(needed for the pre-screen substring gate)"),
)


def register_redaction_patterns(patterns, source: str = "plugin") -> int:
    """Additively register credential-token regexes; returns the count accepted.

    Invalid entries (non-compiling, top-level alternation, nested unbounded
    quantifiers, < 2 literal prefix chars) and duplicates are warned/skipped,
    never raised — a broken plugin must not break startup.
    """
    accepted = []
    for pattern in patterns or []:
        if not isinstance(pattern, str) or not pattern.strip():
            logger.warning("%s: skipping empty/non-string redaction pattern", source)
            continue
        pattern = pattern.strip()
        try:
            re.compile(pattern)
        except re.error as exc:
            logger.warning("%s: skipping invalid redaction pattern %r (%s)", source, pattern, exc)
            continue
        rejected = next((message for reject, message in _PATTERN_REJECT_RULES if reject(pattern)), None)
        if rejected:
            logger.warning(rejected, source, pattern)
            continue
        if pattern in _PREFIX_PATTERNS or pattern in _plugin_patterns() or pattern in accepted:
            logger.debug("%s: redaction pattern %r already registered", source, pattern)
            continue
        accepted.append(pattern)

    if accepted:
        with _registry_lock:
            _PLUGIN_PREFIX_PATTERNS.setdefault(source, []).extend(accepted)
            _rebuild_prefix_matcher()
        logger.info("%s: registered %d redaction pattern(s)", source, len(accepted))
    return len(accepted)


def _reset_plugin_redaction_patterns() -> None:
    """Drop all plugin-registered patterns (tests/teardown only)."""
    with _registry_lock:
        _PLUGIN_PREFIX_PATTERNS.clear()
        _rebuild_prefix_matcher()


class RedactingFormatter(logging.Formatter):
    """Log formatter that redacts secrets from all log messages."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_text(super().format(record))
