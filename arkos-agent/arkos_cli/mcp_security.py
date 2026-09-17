"""Security checks for user-configured MCP server entries.

Blocks three narrow shapes (see ``validate_mcp_server_entry``), including a hardcoded IOC blocklist
for the June 2026 arkos-0day campaign. Runs BOTH at save time (``_save_mcp_server`` — dashboard API +
CLI) and at spawn time (``tools.mcp_tool._filter_suspicious_mcp_servers``), so a hand-edited or
pre-planted ``config.yaml`` entry is caught before it can execute.
"""
from __future__ import annotations

import os
import re
import shlex
from typing import Any

_SHELL_INTERPRETERS = frozenset({
    "bash", "sh", "zsh", "dash", "fish", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
})

_EGRESS_PATTERN = re.compile(
    r"(?<![\w.-])(?:curl|wget|nc|ncat|socat)(?![\w.-])"
    r"|/dev/tcp/"
    r"|\bInvoke-WebRequest\b"
    r"|\bInvoke-RestMethod\b"
    r"|\bSystem\.Net\.WebClient\b",
    re.IGNORECASE,
)

_EXFIL_HINT_PATTERN = re.compile(
    r"\.env\b|--data-binary|--data-raw|\b-X\s+POST\b|\bPOST\b|<\s*[^\s]+",
    re.IGNORECASE,
)

_PERSISTENCE_PATTERN = re.compile(
    r"authorized_keys"
    r"|\.ssh/"
    r"|/etc/ssh\b"
    r"|/etc/pam\.d\b|pam_[\w-]+\.so"
    r"|/etc/sudoers"
    r"|/etc/cron|crontab\b"
    r"|/etc/rc\.local|/etc/systemd"
    r"|\.bashrc\b|\.bash_profile\b|\.profile\b|\.zshrc\b",
    re.IGNORECASE,
)

_IOC_SUBSTRINGS = (
    "AAAAC3NzaC1lZDI1NTE5AAAAICBoh1oDC4DnsO1m5mJ4yfEKrQebaFh",
    "arkos-0day",
    "60.165.167.",
    "118.182.244.156",
    "61.178.123.196",
)


def _command_basename(command: Any) -> str:
    text = str(command or "").strip()
    if not text:
        return ""
    try:
        parts = shlex.split(text, posix=(os.name != "nt"))
    except ValueError:
        parts = text.split()
    first = parts[0] if parts else text
    return os.path.basename(first).lower()


def _inline_script(args: Any) -> str:
    if args is None:
        return ""
    if isinstance(args, (list, tuple)):
        return " ".join(str(item) for item in args)
    return str(args)


def _entry_text(entry: dict[str, Any]) -> str:
    """Flatten command + args + env values into one string for IOC scanning."""
    parts: list[str] = [str(entry.get("command") or "")]
    parts.append(_inline_script(entry.get("args")))
    env = entry.get("env")
    if isinstance(env, dict):
        parts.extend(str(v) for v in env.values())
    return " ".join(parts)


def validate_mcp_server_entry(name: str, entry: dict[str, Any]) -> list[str]:
    """Return security warnings for an MCP server entry (empty = not suspicious).

    Intentionally not a whitelist — custom commands, Python scripts, npx, uvx stay legal. Only three
    narrow shapes are blocked: (1) a known IOC anywhere in command/args/env, (2) a shell interpreter
    with network egress in its inline script, (3) a shell interpreter writing an OS persistence surface.

    * a shell interpreter whose inline script writes to an OS persistence surface (June 2026 arkos-0day
    SSH/PAM/sudoers/cron shape)..
    """
    if not isinstance(entry, dict):
        return []

    issues: list[str] = []
    flat = _entry_text(entry)
    for ioc in _IOC_SUBSTRINGS:
        if ioc in flat:
            issues.append(
                f"MCP server '{name}' contains a known arkos-0day "
                f"indicator-of-compromise ('{ioc}')"
            )
            return issues

    command = entry.get("command")
    if _command_basename(command) not in _SHELL_INTERPRETERS:
        return issues
    script = _inline_script(entry.get("args"))
    if not script:
        return issues

    if _EGRESS_PATTERN.search(script):
        issue = (
            f"MCP server '{name}' uses shell interpreter '{command}' with "
            f"network egress in args"
        )
        if _EXFIL_HINT_PATTERN.search(script):
            issue += " and exfiltration-shaped arguments"
        issues.append(issue)
    if _PERSISTENCE_PATTERN.search(script):
        issues.append(
            f"MCP server '{name}' uses shell interpreter '{command}' to write "
            f"to an OS persistence surface (SSH keys / PAM / sudoers / cron / "
            f"shell rc) — this is the arkos-0day backdoor shape, not a real "
            f"MCP server"
        )
    return issues



def is_mcp_server_entry_suspicious(name: str, entry: dict[str, Any]) -> bool:
    return bool(validate_mcp_server_entry(name, entry))
