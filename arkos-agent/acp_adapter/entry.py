"""CLI entry point for the arkos-agent ACP adapter.

Loads ``~/.arkos/.env``, routes logging to stderr (stdout is reserved for ACP
JSON-RPC), and starts the ACP agent server.

Usage::

    python -m acp_adapter.entry   # or: arkos acp / arkos-acp
"""

try:
    import arkos_bootstrap  # noqa: F401
except ModuleNotFoundError:
    pass
else:
    arkos_bootstrap.harden_import_path()

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from arkos_constants import get_arkos_home


_BENIGN_PROBE_METHODS = frozenset({"ping", "health", "healthcheck"})


class _BenignProbeMethodFilter(logging.Filter):
    """Suppress acp 'Background task failed' tracebacks caused by unknown liveness-probe methods
    (e.g. ``ping``); every other background-task error, incl. method_not_found for non-probe
    methods, stays visible."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage() != "Background task failed" or not record.exc_info:
            return True
        try:
            from acp.exceptions import RequestError
        except ImportError:
            return True
        exc = record.exc_info[1]
        if not isinstance(exc, RequestError) or getattr(exc, "code", None) != -32601:
            return True
        data = getattr(exc, "data", None)
        return not (isinstance(data, dict) and data.get("method") in _BENIGN_PROBE_METHODS)


def _setup_logging() -> None:
    """Route all logging to stderr so stdout stays clean for ACP stdio."""
    from agent.redact import RedactingFormatter

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                                            datefmt="%Y-%m-%d %H:%M:%S"))
    handler.addFilter(_BenignProbeMethodFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for noisy in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _load_env() -> None:
    """Load .env from ARKOS_HOME (default ``~/.arkos``)."""
    from arkos_cli.env_loader import load_arkos_dotenv

    arkos_home = get_arkos_home()
    loaded = load_arkos_dotenv(arkos_home=arkos_home)
    log = logging.getLogger(__name__)
    for env_file in loaded or ():
        log.info("Loaded env from %s", env_file)
    if not loaded:
        log.info("No .env found at %s, using system env", arkos_home / ".env")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="arkos-acp", description="Run Arkos Agent as an ACP stdio server.")
    parser.add_argument("--version", action="store_true", help="Print Arkos version and exit")
    parser.add_argument("--check", action="store_true", help="Verify ACP dependencies and adapter imports, then exit")
    parser.add_argument("--setup", action="store_true",
                        help="Run interactive Arkos provider/model setup for ACP terminal auth")
    parser.add_argument("--setup-browser", action="store_true",
                        help="Install agent-browser + Playwright Chromium into ~/.arkos/node/ "
                             "for browser tool support. Idempotent.")
    parser.add_argument("--yes", "-y", action="store_true", dest="assume_yes",
                        help="Accept all prompts (currently used by --setup-browser to skip the "
                             "~400 MB Chromium download confirmation).")
    return parser.parse_args(argv)


def _print_version() -> None:
    from arkos_cli import __version__ as arkos_version

    print(arkos_version)


def _run_check() -> None:
    import acp  # noqa: F401
    from acp_adapter.server import ArkosACPAgent  # noqa: F401

    print("Arkos ACP check OK")


def _run_setup() -> None:
    from arkos_cli.main import main as arkos_main

    old_argv = sys.argv[:]
    try:
        sys.argv = [old_argv[0] if old_argv else "arkos", "model"]
        arkos_main()
    finally:
        sys.argv = old_argv

    if not sys.stdin.isatty():
        return
    try:
        reply = input("\nInstall browser tools? Downloads agent-browser (npm) and "
                      "optionally Playwright Chromium (~400 MB). [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if reply in {"y", "yes"}:
        _run_setup_browser(assume_yes=False)


_SETUP_BROWSER_STEPS = (
    ("node", "Node.js installation failed — cannot proceed with browser tools."),
    ("browser", "Browser tools installation failed."),
)


def _run_setup_browser(assume_yes: bool = False) -> int:
    """Bootstrap agent-browser + Chromium via dep_ensure -> install.{sh,ps1}
    --ensure (shared with the runtime lazy installer). Returns 0 on success, 1 on failure."""
    from arkos_cli.dep_ensure import ensure_dependency

    try:
        for dep, failure_msg in _SETUP_BROWSER_STEPS:
            if not ensure_dependency(dep, interactive=not assume_yes):
                print(failure_msg, file=sys.stderr)
                return 1
        return 0
    except OSError as exc:
        print(f"Browser bootstrap failed: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> None:
    """Entry point: load env, configure logging, run the ACP agent."""
    args = _parse_args(argv)
    for flag, action in (("version", _print_version), ("check", _run_check), ("setup", _run_setup)):
        if getattr(args, flag):
            return action()
    if args.setup_browser:
        if rc := _run_setup_browser(assume_yes=args.assume_yes):
            sys.exit(rc)
        return

    _setup_logging()
    _load_env()

    logger = logging.getLogger(__name__)
    logger.info("Starting arkos-agent ACP adapter")

    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    import acp
    from .server import ArkosACPAgent

    if os.environ.get("ARKOS_ACP_SKIP_CONFIGURED_MCP", "").strip() != "1":
        try:
            from arkos_cli.mcp_startup import start_background_mcp_discovery

            start_background_mcp_discovery(logger=logger, thread_name="acp-mcp-discovery")
        except Exception:
            logger.debug("MCP tool discovery failed at ACP startup", exc_info=True)

    agent = ArkosACPAgent()
    try:
        asyncio.run(acp.run_agent(agent, use_unstable_protocol=True))
    except KeyboardInterrupt:
        logger.info("Shutting down (KeyboardInterrupt)")
    except Exception:
        logger.exception("ACP agent crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
