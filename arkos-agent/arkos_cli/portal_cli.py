"""``arkos portal`` — the human-readable entry point for Arkos Portal."""
from __future__ import annotations

import sys
import webbrowser

from arkos_cli.colors import Colors, color
from arkos_cli.config import load_config

DEFAULT_PORTAL_URL = ""
SUBSCRIPTION_URL = ""
DOCS_URL = "https://arkos.local/docs/user-guide/features/tool-gateway"
_CATALOG = [
    ("web", "Web search & extract", "Firecrawl"),
    ("image_gen", "Image generation", "FAL"),
    ("tts", "Text-to-speech", "OpenAI TTS"),
    ("browser", "Browser automation", "Browser Use"),
    ("modal", "Cloud terminal", "Modal"),
]


def _feature_state(feat, *, via_portal: str) -> str:
    """Routing column shared by `portal info` and `portal tools`."""
    if feat.managed_by_portal:
        return color(via_portal, Colors.GREEN)
    if feat.active:
        return feat.current_provider or "active"
    return color("not configured", Colors.DIM)


def _heading(title: str) -> None:
    print()
    print(color(f"  {title}", Colors.MAGENTA))
    print(color("  " + "─" * len(title), Colors.MAGENTA))


def _cmd_status(args) -> int:
    """Show Portal auth + Tool Gateway routing summary."""
    from arkos_cli.auth import get_portal_auth_status_local
    from arkos_cli.portal_subscription import get_portal_subscription_features

    config = load_config() or {}
    try:
        auth = get_portal_auth_status_local() or {}
    except Exception:
        auth = {}
    logged_in = bool(auth.get("logged_in"))
    _heading("Arkos Portal")
    if logged_in:
        print(f"  Auth:    {color('✓ logged in', Colors.GREEN)}")
        print(f"  Portal:  {auth.get('portal_base_url') or DEFAULT_PORTAL_URL}")
        if auth.get("inference_base_url"):
            print(f"  API:     {auth['inference_base_url']}")
    else:
        print(f"  Auth:    {color('not logged in', Colors.YELLOW)}")
        print(f"  Sign up: {SUBSCRIPTION_URL}")
        print("  Login:   arkos portal")

    model_cfg = config.get("model") if isinstance(config.get("model"), dict) else {}
    provider = str(model_cfg.get("provider") or "").strip().lower()
    if provider == "portal":
        print(f"  Model:   {color('✓ using Portal as inference provider', Colors.GREEN)}")
    elif provider:
        print(f"  Model:   currently {provider} (switch with `arkos model`)")

    _heading("Tool Gateway")
    try:
        features = get_portal_subscription_features(config)
    except Exception:
        print("  (could not resolve subscription state)")
        return 0
    rows = [(feat.label, _feature_state(feat, via_portal="via Arkos Portal")) for feat in features.items()]
    width = max((len(r[0]) for r in rows), default=0)
    for label, state in rows:
        print(f"  {label:<{width}}   {state}")
    if not logged_in:
        print()
        print(color(f"  Docs: {DOCS_URL}", Colors.DIM))
    return 0


def _cmd_open(args) -> int:
    """Open the Portal subscription page in the default browser."""
    print(f"Opening {SUBSCRIPTION_URL}")
    try:
        opened = webbrowser.open(SUBSCRIPTION_URL)
    except Exception:
        opened = False
    if opened:
        return 0
    print()
    print("Could not launch a browser. Visit the URL above manually.")
    return 1


def _cmd_tools(args) -> int:
    """List the Tool Gateway catalog + current routing."""
    from arkos_cli.portal_subscription import get_portal_subscription_features

    config = load_config() or {}
    try:
        features = get_portal_subscription_features(config)
    except Exception:
        print("Could not resolve Tool Gateway state.", file=sys.stderr)
        return 1

    _heading("Tool Gateway catalog")
    if not features.portal_auth_present:
        print(color("  Not logged into Arkos Portal — sign in with `arkos portal`.", Colors.YELLOW))
        print()

    label_width = max(len(label) for _, label, _ in _CATALOG)
    for key, label, partner in _CATALOG:
        feat = features.features.get(key)
        state = color("unknown", Colors.DIM) if feat is None else _feature_state(feat, via_portal="✓ via Arkos Portal")
        print(f"  {label:<{label_width}}  partner: {partner:<14} {state}")

    print()
    print(color(f"  Manage your subscription: {SUBSCRIPTION_URL}", Colors.DIM))
    print(color(f"  Docs: {DOCS_URL}", Colors.DIM))
    return 0


def _cmd_login(args) -> int:
    """One-shot Arkos Portal onboarding (login + model + provider + tools).

    Reuses the exact wiring behind ``arkos setup --portal`` so the commands stay in lockstep.
    """
    from arkos_cli.setup import _run_portal_one_shot

    config = load_config() or {}
    try:
        _run_portal_one_shot(config)
    except (KeyboardInterrupt, EOFError):
        print()
        print("Portal setup cancelled.")
        return 1
    return 0


_SUBCOMMANDS = {
    None: _cmd_login,
    "": _cmd_login,
    "login": _cmd_login,
    "info": _cmd_status,
    "status": _cmd_status,
    "open": _cmd_open,
    "tools": _cmd_tools,
}


def portal_command(args) -> int:
    """Top-level dispatch for `arkos portal <subcommand>`."""
    sub = getattr(args, "portal_command", None)
    handler = _SUBCOMMANDS.get(sub)
    if handler is not None:
        return handler(args)
    print(f"Unknown portal subcommand: {sub}", file=sys.stderr)
    print("Run `arkos portal -h` for usage.", file=sys.stderr)
    return 1


def add_parser(subparsers) -> None:
    """Register `arkos portal` on the given argparse subparsers object."""
    portal_parser = subparsers.add_parser(
        "portal",
        help="Set up Arkos Portal (login, model pick, Tool Gateway); see also `portal info`",
        description=(
            "Run `arkos portal` with no subcommand to log in to Arkos Portal "
            "and set it up — pick a model, set Portal as your provider, and offer "
            "the Tool Gateway (the human-readable alias for `arkos auth add "
            "portal --type oauth`, identical to `arkos setup --portal`). "
            "Subcommands: login (default), info, open, tools."
        ),
    )
    portal_sub = portal_parser.add_subparsers(dest="portal_command")

    for name, help_text in (
        ("login", "Log in to Arkos Portal + set it up (default; one-shot onboarding)"),
        ("info", "Show Portal auth + Tool Gateway routing summary"),
        ("status", None),
        ("open", "Open the Portal subscription page in your default browser"),
        ("tools", "List Tool Gateway tools and which are routed via Portal"),
    ):
        portal_sub.add_parser(name, **({} if help_text is None else {"help": help_text}))

    portal_parser.set_defaults(func=portal_command)
