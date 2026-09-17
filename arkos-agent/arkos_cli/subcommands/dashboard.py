"""``arkos dashboard`` / ``arkos serve`` subcommand parsers.

``dashboard`` is the browser web UI; ``serve`` is the same gateway, headless —
what the desktop app and remote backends run. ``serve`` also skips the web UI
build (``headless_backend=True``): pure JSON-RPC/WS clients never load the SPA.
Both share one handler (``cmd_dashboard`` → ``start_server``).
"""

from __future__ import annotations

import argparse
from typing import Callable


def _add_server_runtime_args(parser) -> None:
    """Runtime flags shared by ``dashboard`` and ``serve`` (same ``web_server.start_server``)."""
    parser.add_argument(
        "--port", type=int, default=9119, help="Port (default 9119, 0 for auto-assign by OS)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default 127.0.0.1)")
    parser.add_argument(
        "--insecure", action="store_true",
        help="DEPRECATED / NO-OP. Formerly bypassed auth on a non-loopback "
            "bind. As of the June 2026 hardening it no longer disables "
            "authentication — a public bind always requires an auth provider "
            "(password or OAuth). Bind 127.0.0.1 + tunnel to keep it local.")
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip the web UI build step and serve the existing dist directly. "
            "Useful for non-interactive contexts (Windows Scheduled Tasks, CI) "
            "where npm may not be available. Pre-build with: cd web && npm run build")
    parser.add_argument(
        "--isolated", action="store_true",
        help="When launched from a named profile, run a dedicated server scoped "
            "to that profile instead of routing to the machine-level server. "
            "Default behavior is unified: profile launches attach to (or start) "
            "ONE machine-level server and preselect the profile.")
    parser.add_argument("--open-profile", dest="open_profile", default="", help=argparse.SUPPRESS)
    parser.add_argument(
        "--stop", action="store_true", help="Stop all running Arkos web server processes and exit")
    parser.add_argument(
        "--status", action="store_true", help="List running Arkos web server processes and exit")


def _configure_serve_parser(parser, *, cmd_dashboard: Callable) -> None:
    """Canonical ``serve`` arguments; shared by the full tree and Desktop's lean hot-path parser."""
    _add_server_runtime_args(parser)
    parser.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--ssh-session-token-file", dest="ssh_session_token_file", metavar="PATH", default=None,
        help="Read a one-shot Desktop SSH session token from PATH")
    parser.add_argument(
        "--ssh-owner-nonce", dest="ssh_owner_nonce", metavar="NONCE", default=None,
        help="Identify a Desktop-owned SSH backend process")
    parser.set_defaults(func=cmd_dashboard, no_open=True, headless_backend=True, command="serve")


def build_serve_parser(
    *, cmd_dashboard: Callable, add_help: bool = True, exit_on_error: bool = True,
) -> argparse.ArgumentParser:
    """Build the standalone parser used by the lean ``serve`` dispatch path."""
    parser = argparse.ArgumentParser(
        prog="arkos serve",
        description="Run the Arkos backend server - the JSON-RPC/WebSocket gateway the "
            "desktop app and remote clients connect to. Headless: it never opens "
            "a browser UI.",
        add_help=add_help, exit_on_error=exit_on_error)
    _configure_serve_parser(parser, cmd_dashboard=cmd_dashboard)
    return parser


def build_dashboard_parser(
    subparsers, *, cmd_dashboard: Callable, cmd_dashboard_register: Callable) -> None:
    """Attach ``dashboard`` (browser UI) and ``serve`` (headless backend the desktop spawns)."""
    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Start the web UI dashboard",
        description="Launch the Arkos web dashboard for managing config, API keys, and sessions",
    )
    _add_server_runtime_args(dashboard_parser)
    dashboard_parser.add_argument(
        "--no-open", action="store_true", help="Don't open browser automatically")
    dashboard_parser.add_argument("--tui", action="store_true", help=argparse.SUPPRESS)
    dashboard_parser.set_defaults(func=cmd_dashboard)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the Arkos backend server (headless; powers the desktop app and remote backends)",
        description="Run the Arkos backend server — the JSON-RPC/WebSocket gateway the "
            "desktop app and remote clients connect to. Headless: it never opens "
            "a browser UI.")
    _configure_serve_parser(serve_parser, cmd_dashboard=cmd_dashboard)

    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_subcommand")
    dashboard_register_parser = dashboard_subparsers.add_parser(
        "register",
        help="Register a self-hosted dashboard with Arkos Portal (writes the OAuth client ID to .env)",
        description="Register this install as a self-hosted dashboard with your Portal "
            "Portal account. Creates an OAuth client, writes "
            "ARKOS_DASHBOARD_OAUTH_CLIENT_ID into ~/.arkos/.env, and prints "
            "how to engage the login gate. Requires being logged in (arkos setup).")
    dashboard_register_parser.add_argument(
        "--name", default=None,
        help="Human-readable label for the dashboard (default: an auto-generated name)")
    dashboard_register_parser.add_argument(
        "--redirect-uri", dest="redirect_uri", default=None,
        help="Optional public HTTPS OAuth redirect URI for the dashboard, e.g. "
            "https://arkos.example.com/auth/callback. Omit for localhost-only use.")
    dashboard_register_parser.add_argument(
        "--portal-url", dest="portal_url", default=None,
        help="Override the Arkos Portal base URL for registration (default: the "
            "portal you logged into). The access token must be valid at this "
            "portal. Also settable via ARKOS_DASHBOARD_PORTAL_URL. Mainly for "
            "testing against a staging/preview portal.")
    dashboard_register_parser.set_defaults(func=cmd_dashboard_register)
