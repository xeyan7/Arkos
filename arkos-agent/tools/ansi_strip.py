"""Strip ANSI escape sequences from subprocess output so they never reach the
model's context (models otherwise copy them into file writes). Covers full
ECMA-48: CSI, OSC (BEL/ST), DCS/SOS/PM/APC, nF, Fp/Fe/Fs and 8-bit C1 controls."""

import re

_ANSI_ESCAPE_RE = re.compile(
    r"\x1b"
    r"(?:"
        r"\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]"
        r"|\][\s\S]*?(?:\x07|\x1b\\)"
        r"|[PX^_][\s\S]*?(?:\x1b\\)"
        r"|[\x20-\x2f]+[\x30-\x7e]"
        r"|[\x30-\x7e]"
    r")"
    r"|\x9b[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]"
    r"|\x9d[\s\S]*?(?:\x07|\x9c)"
    r"|[\x80-\x9f]",
    re.DOTALL,
)
_HAS_ESCAPE = re.compile(r"[\x1b\x80-\x9f]")
_HAS_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_HAS_UNICODE_TAG = re.compile(r"[\U000E0000-\U000E007F]")

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_UNICODE_TAG_SUB_RE = re.compile(
    r"(\U0001F3F4[\U000E0020-\U000E007E]+\U000E007F)"
    r"|[\U000E0000-\U000E007F]"
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences; clean text passes through unchanged (fast path)."""
    if not text or not _HAS_ESCAPE.search(text):
        return text
    return _ANSI_ESCAPE_RE.sub("", text)


def sanitize_display_text(text: str) -> str:
    """Sanitize stored/untrusted text before echoing it to a terminal: strips ANSI
    sequences AND bare control chars, keeping only newlines/tabs (CRs become newlines
    so ``\\r``-overwrite spoofing can't hide content). Rich's ``Text`` does NOT
    neutralize raw escape bytes, so a replayed ``/resume`` message must not be able
    to clear the screen, retitle the window, or restyle UI.

    Use this when re-rendering conversation history or other persisted text in a terminal UI (e.g. the
    ``/resume`` recap): a message that arrived with embedded escapes — pasted content, gateway-origin text,
    or model output echoing injected tool results — must not be able to clear the screen, retitle the
    window, move the cursor, or restyle adjacent UI when replayed. Mirrors 
    (``sanitize_user_text``).
    """
    if not text or not _HAS_CONTROL.search(text):
        return text
    text = strip_ansi(text)
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_CHARS_RE.sub("", text)


def strip_unicode_tags(text: str) -> str:
    """Remove invisible Unicode TAG chars (a prompt-injection smuggling channel in
    untrusted tool output); valid emoji tag sequences are preserved.

    Returns the input unchanged (fast path) when no plane-14 tag characters are present. .
    """
    if not text or not _HAS_UNICODE_TAG.search(text):
        return text
    return _UNICODE_TAG_SUB_RE.sub(lambda m: m.group(1) or "", text)
