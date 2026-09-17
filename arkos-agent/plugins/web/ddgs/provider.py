"""DuckDuckGo search via the optional ``ddgs`` package (search only, no key). ``is_available()``
reflects package importability; the plugin registers either way so ``arkos tools`` can offer to
install it. Isolation: ``ddgs``/``primp`` can block inside native code while holding the GIL, so a
thread-pool ``future.result(timeout=…)`` cap can never fire and Ctrl+C/SIGTERM freeze the process —
each search runs in a disposable child process the parent can terminate/kill.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from plugins.web._common import BaseWebSearchProvider, search_fail, search_ok, setup_schema, title_hit

logger = logging.getLogger(__name__)

_SEARCH_TIMEOUT_SECS = 30
_POLL_INTERVAL_SECS = 0.1
_TERMINATE_GRACE_SECS = 1.0
_test_hook: Optional[str] = None
_last_worker_proc: Optional[subprocess.Popen] = None


class _SearchInterrupted(Exception):
    """Raised when tools.interrupt.is_interrupted() trips during a search wait."""


def _run_ddgs_search(query: str, safe_limit: int) -> list[dict[str, Any]]:
    """Blocking ddgs query → normalized hits (module-level: the child worker imports it,
    tests patch it for in-process runs).

    ``DDGS(timeout=…)`` bounds each individual HTTP request; the overall wall-clock cap is enforced by the
    parent via process timeout.
    """
    from ddgs import DDGS  # type: ignore
    results: list[dict[str, Any]] = []
    with DDGS(timeout=10) as client:
        for i, hit in enumerate(client.text(query, max_results=safe_limit)):
            if i >= safe_limit:
                break
            results.append(title_hit(str(hit.get("title", "")), str(hit.get("href") or hit.get("url") or ""), str(hit.get("body", "")), i + 1))
    return results


def _plugins_path_entry() -> str:
    """``sys.path`` entry that makes ``import plugins`` work in the child (live package
    location first; correct for source checkouts and site-packages)."""
    try:
        import plugins as plugins_pkg
        if pkg_file := getattr(plugins_pkg, "__file__", None):
            return os.path.dirname(os.path.dirname(os.path.abspath(pkg_file)))
    except Exception:  # noqa: BLE001 — fall through to path-walk fallback
        pass
    return os.path.abspath(os.path.join(__file__, *([os.pardir] * 4)))


def _terminate_and_reap(proc: Optional[subprocess.Popen], *, grace: float = _TERMINATE_GRACE_SECS) -> None:
    """Terminate a worker, escalate to kill, and wait so no orphan remains. Does not close
    the parent's pipe ends — closing stdout while another thread is blocked in ``read()``
    deadlocks on some platforms; the caller drains first."""
    if proc is None:
        return
    alive = False

    def _wait_until_dead() -> bool:
        deadline = time.monotonic() + grace
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        return proc.poll() is not None

    try:
        for escalate in (proc.terminate, proc.kill):
            if proc.poll() is None:
                escalate()
                alive = not _wait_until_dead()
        if alive:
            logger.warning("DDGS worker pid=%s did not exit after kill", proc.pid)
    except Exception as exc:  # noqa: BLE001 — best-effort cleanup
        logger.debug("DDGS worker reap error: %s", exc)


def _spawn_worker(env: dict[str, str]) -> subprocess.Popen:
    """Start ``_search_worker.py`` as a script with ``plugins`` importable. Running as a
    script puts ``plugins/web/ddgs/`` on ``sys.path[0]``, breaking ``import plugins...``,
    so the real package location is prepended to PYTHONPATH."""
    child_pythonpath = env.get("PYTHONPATH", "")
    path_entry = _plugins_path_entry()
    if path_entry and path_entry not in child_pythonpath.split(os.pathsep):
        env["PYTHONPATH"] = path_entry + os.pathsep + child_pythonpath if child_pythonpath else path_entry
    worker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_search_worker.py")
    extra_kwargs: dict[str, Any] = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {"start_new_session": True}
    return subprocess.Popen(
        [sys.executable, worker_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=env, text=True, encoding="utf-8", errors="replace", **extra_kwargs,
    )


def _parse_envelope(raw: str, proc: subprocess.Popen) -> list[dict[str, Any]]:
    """Decode the worker's stdout envelope; raise ``RuntimeError`` on any malformed shape."""
    raw = raw.strip()
    if not raw:
        raise RuntimeError(f"DDGS worker exited without a result (code={proc.poll()})")
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"DDGS worker returned invalid JSON: {raw[:200]!r}") from exc
    if not isinstance(envelope, dict):
        raise RuntimeError(f"DDGS worker returned an invalid envelope: {envelope!r}")
    if not envelope.get("ok"):
        raise RuntimeError(str(envelope.get("error") or "DDGS worker failed"))
    results = envelope.get("results") or []
    if not isinstance(results, list):
        raise RuntimeError("DDGS worker returned non-list results")
    return results


def _run_ddgs_search_bounded(query: str, safe_limit: int) -> list[dict[str, Any]]:
    """Run ``_run_ddgs_search`` in a disposable process with a hard deadline. The parent
    never joins a child that may be in native code holding *its* GIL — it polls a
    communicator thread and, on timeout/interrupt, kills the OS process.
    Raises ``TimeoutError``, ``_SearchInterrupted``, or ``RuntimeError``."""
    from tools.interrupt import is_interrupted
    from tools.environments.local import _sanitize_subprocess_env
    global _last_worker_proc
    request: dict[str, Any] = {"query": query, "safe_limit": safe_limit}
    env = _sanitize_subprocess_env(dict(os.environ))
    if _test_hook:
        request["test_hook"] = _test_hook
        env["ARKOS_DDGS_ALLOW_TEST_HOOKS"] = "1"
    proc = _last_worker_proc = _spawn_worker(env)
    pool = cf.ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(proc.communicate, json.dumps(request))
    interrupted, done, raw = False, False, ""
    try:
        deadline = time.monotonic() + _SEARCH_TIMEOUT_SECS
        while not done and not (interrupted := is_interrupted()) and (remaining := deadline - time.monotonic()) > 0:
            try:
                raw, done = fut.result(timeout=min(_POLL_INTERVAL_SECS, remaining))[0] or "", True
            except cf.TimeoutError:
                pass
    finally:
        _terminate_and_reap(proc)
        if not fut.done():
            try:
                raw = raw or fut.result(timeout=_TERMINATE_GRACE_SECS)[0] or ""
            except Exception:  # noqa: BLE001
                pass
        pool.shutdown(wait=False, cancel_futures=True)
    if interrupted:
        raise _SearchInterrupted("DuckDuckGo search interrupted")
    if not done:
        raise TimeoutError(f"DuckDuckGo search timed out after {_SEARCH_TIMEOUT_SECS}s")
    return _parse_envelope(raw, proc)


class DDGSWebSearchProvider(BaseWebSearchProvider):
    """DuckDuckGo HTML-scrape search provider (no API key; DDG rate-limits server-side).
    ddgs errors surface as ``{"success": False, "error": ...}`` rather than raising."""

    NAME = "ddgs"
    DISPLAY_NAME = "DuckDuckGo (ddgs)"

    def is_available(self) -> bool:
        """True when ``ddgs`` is importable. Must NOT do network I/O — runs at
        tool-registration time and on every ``arkos tools`` paint."""
        try:
            import ddgs  # noqa: F401
            return True
        except ImportError:
            return False

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Run the search in a disposable child with a hard wall-clock timeout so a
        hung native ``primp`` call cannot freeze the Arkos process..
        """
        if not self.is_available():
            return search_fail("ddgs package is not installed — run `pip install ddgs`")
        try:
            web_results = _run_ddgs_search_bounded(query, max(1, int(limit)))
        except TimeoutError:
            logger.warning("DDGS search timed out after %ds for query: %r", _SEARCH_TIMEOUT_SECS, query)
            return search_fail(
                f"DuckDuckGo search timed out after {_SEARCH_TIMEOUT_SECS}s — "
                "DuckDuckGo may be rate-limiting or slow. Try again later or switch to a different search provider."
            )
        except _SearchInterrupted:
            logger.info("DDGS search interrupted for query: %r", query)
            return search_fail("DuckDuckGo search interrupted")
        except Exception as exc:  # noqa: BLE001 — ddgs raises its own exceptions
            logger.warning("DDGS search error: %s", exc)
            return search_fail(f"DuckDuckGo search failed: {exc}")
        logger.info("DDGS search '%s': %d results (limit %d)", query, len(web_results), limit)
        return search_ok(web_results)

    def get_setup_schema(self) -> Dict[str, Any]:
        return setup_schema(
            "DuckDuckGo (ddgs)", "free · no key · search only",
            "Search via the ddgs Python package — no API key (pair with any extract provider)", post_setup="ddgs",
        )




_PLUGIN_COMPAT_LAZY = {
    'WebSearchProvider': ('agent.web_search_provider', 'WebSearchProvider'),
}


def __getattr__(name):
    target = _PLUGIN_COMPAT_LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    from arkos_cli.plugin_compat import warn_once
    warn_once(__name__, name, *target)
    return getattr(importlib.import_module(target[0]), target[1])
