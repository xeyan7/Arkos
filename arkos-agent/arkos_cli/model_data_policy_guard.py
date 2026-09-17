"""Data-policy confirmation helpers for model selection surfaces.

Some inference tiers are cheap *because* the vendor trains on your prompts. A static rule table (not
a ProviderProfile hook) because the guard runs inside core selection code (``auth.py`` /
``web_server.py``), which never calls into the active provider profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class DataTrainingWarning:
    """Confirmation payload for models whose tier trains on user data."""

    model: str
    provider: str
    message: str



def _is_meta_contributor(model_lower: str, provider_lower: str) -> bool:
    return model_lower.endswith("-contributor") or "contributor" in model_lower.split("-")


_META_CONTRIBUTOR_MESSAGE = (
    "!!! CONTRIBUTOR TIER — TRAINS ON YOUR DATA !!!\n"
    "\n"
    "This is Meta's contributor tier. Selecting it permits Meta to use your\n"
    "prompts and completions to train future Meta models.\n"
    "\n"
    "See current pricing and rate limits for the Meta Model API here:\n"
    "  https://dev.meta.ai/docs/pricing-rate-limits/\n"
    "\n"
    "It lowers the barrier to entry for prototyping, testing integrations, and\n"
    "scaling experiments where training on your data is acceptable. Do NOT use it\n"
    "for confidential, proprietary, personal, or otherwise sensitive data. For the\n"
    "same model with no training on your data, select the standard variant\n"
    "(without the -contributor suffix).\n"
    "\n"
    "Confirm only if training on your prompts and completions is acceptable."
)


_RULES: tuple[tuple[Callable[[str, str], bool], str], ...] = (
    (_is_meta_contributor, _META_CONTRIBUTOR_MESSAGE),
)


def data_training_warning(
    model_name: str,
    *,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,  # noqa: ARG001 — reserved for host-scoped rules
) -> Optional[DataTrainingWarning]:
    """Warning payload when *model_name* selects a data-training tier, else ``None``. Call after model
    resolution; surface ``.message`` as a confirm prompt."""
    model = (model_name or "").strip()
    if not model:
        return None
    model_lower, provider_lower = model.lower(), (provider or "").strip().lower()
    for predicate, message in _RULES:
        try:
            if predicate(model_lower, provider_lower):
                return DataTrainingWarning(model=model, provider=(provider or "").strip(), message=message)
        except Exception:
            continue
    return None
