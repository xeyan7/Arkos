"""Default SOUL.md template seeded into ARKOS_HOME on first run."""

DEFAULT_SOUL_MD = (
    "You are Arkos, an autonomous AI desktop assistant designed for high efficiency, clarity, and precision. "
    "Be direct: match the length and depth of your response to the complexity of the request. Provide concise "
    "answers for straightforward questions, and structured summaries of changes, validations, and next steps for "
    "completed tasks without unnecessary process narration. No filler phrases, no echoing the user's prompt, and no "
    "redundant restatements. Communicate with factual clarity, acknowledge uncertainties openly, and prioritize "
    "producing robust, verified results."
)

_SCAFFOLD_HEAD = (
    "# Arkos Persona\n\n<!--\nThis file defines the agent's personality and tone.\n"
    "The agent will embody whatever you write here.\nEdit this to customize how Arkos communicates with you.\n\n"
)
_SCAFFOLD_TAIL = (
    "This file is loaded fresh each message -- no restart needed.\n"
    "Delete the contents (or this file) to use the default personality.\n-->"
)


def _normalize_soul(text: str) -> str:
    """Unify line endings, strip a leading UTF-8 BOM, trim whitespace."""
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()


def is_legacy_template_soul(text: str) -> bool:
    """True if ``text`` is a non-customized, auto-seeded SOUL.md.

    A file that is empty, matches the default seed, or contains only comment scaffolding carries
    zero user intent and is safe to upgrade in place. Any user customization makes this return False.
    """
    normalized = _normalize_soul(text)
    if not normalized or normalized == _normalize_soul(DEFAULT_SOUL_MD):
        return True
    if normalized.startswith("<!--") and normalized.endswith("-->"):
        return True
    if normalized.startswith("# Arkos Persona") and "<!--" in normalized and normalized.endswith("-->"):
        stripped = normalized.replace("# Arkos Persona", "").strip()
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            return True
    return False
