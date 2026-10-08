"""Shared FAL.ai SDK plumbing: lazy import and small helpers.

Stateful pieces (cache globals, ``_submit_fal_request``)
intentionally stay on :mod:`tools.image_generation_tool`: it is the patch target for the
test suites and for ``plugins/image_gen/fal/``'s ``_it`` indirection, so moving the caches
here would separate the facade from its shared state.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union
from urllib.parse import urlencode


def import_fal_client() -> Any:
    """Import ``fal_client`` (via ``lazy_deps`` when available); raises ImportError if unavailable.

    Callers cache the result on their own module global so tests can monkeypatch it.
    """
    try:
        from tools.lazy_deps import ensure as _lazy_ensure
        _lazy_ensure("image.fal", prompt=False)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 — lazy_deps surfaces install hints
        raise ImportError(str(exc))
    import fal_client  # type: ignore  # noqa: WPS433 — intentionally lazy
    return fal_client


def _extract_http_status(exc: BaseException) -> Optional[int]:
    """HTTP status from httpx (``.response.status_code``) or fal_client (``.status_code``) exceptions, else None."""
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    status = getattr(exc, "status_code", None)
    return status if isinstance(status, int) else None
