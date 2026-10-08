"""Secret-safe tool previews and failure classification for engine callbacks and logs."""


import re


from pathlib import Path


from typing import Any, Iterator


from utils import safe_json_loads


from agent.redact import redact_sensitive_text


from agent.tool_result_classification import file_mutation_result_landed


_tool_preview_max_len: int = 0


def _oneline(text: str) -> str:
    """Collapse whitespace (including newlines) to single spaces."""
    return " ".join(text.split())


def _tail_trunc(text: str, limit: int) -> str:
    """Tail-truncate to ``limit`` chars with ``...`` (0 = unlimited; no guard for limit <= 3)."""
    return text[:limit - 3] + "..." if limit > 0 and len(text) > limit else text


def _truncate_preview(text: str, max_len: int | None) -> str:
    if max_len and max_len > 0 and len(text) > max_len:
        return "." * max_len if max_len <= 3 else text[:max_len - 3] + "..."
    return text


def _clip(text: str, n: int) -> str:
    """``text[:n]`` plus ``...`` when longer (used inside quoted previews)."""
    return f"{text[:n]}{'...' if len(text) > n else ''}"


_SHELL_SILENT_HEADS = {"cd", "pushd", "popd", "export", "set", "unset", "source", ".", "true", "false", ":"}


_SHELL_PIPE_TAIL_HEADS = {"head", "tail", "wc", "sort", "uniq"}


def _shell_basename(head: str) -> str:
    return head.rsplit("/", 1)[-1] if head else ""


def _scan_quoted(text: str) -> Iterator[tuple[int, str, bool]]:
    """Yield ``(index, char, inside_quotes)``; a quote closes unless backslash-escaped."""
    quote: str | None = None
    for i, ch in enumerate(text):
        if quote:
            yield i, ch, True
            if ch == quote and (i == 0 or text[i - 1] != "\\"):
                quote = None
        elif ch in {"'", '"'}:
            quote = ch
            yield i, ch, True
        else:
            yield i, ch, False


def _split_shell_words(segment: str) -> list[str]:
    parts: list[list[str]] = [[]]
    for _, ch, quoted in _scan_quoted(segment):
        if not quoted and ch.isspace():
            parts.append([])
        else:
            parts[-1].append(ch)
    return ["".join(p) for p in parts if p]


def _strip_shell_pipe_tail(segment: str) -> str:
    """Drop a trailing ``| head/tail/wc/sort/uniq ...`` pipeline stage."""
    words = _split_shell_words(segment)
    for i, word in enumerate(words):
        if word == "|" and _shell_basename(words[i + 1] if i + 1 < len(words) else "") in _SHELL_PIPE_TAIL_HEADS:
            words = words[:i]
            break
    return " ".join(words).strip()


def _split_shell_compound(command: str) -> list[str]:
    """Split on unquoted ``&&`` / ``||`` / ``;`` / newline, dropping pipe tails per segment."""
    raw: list[list[str]] = [[]]
    skip = False
    for i, ch, quoted in _scan_quoted(command):
        if skip:
            skip = False
        elif not quoted and (command.startswith("&&", i) or command.startswith("||", i)):
            raw.append([])
            skip = True
        elif not quoted and ch in {";", "\n"}:
            raw.append([])
        else:
            raw[-1].append(ch)
    segments = (_strip_shell_pipe_tail("".join(buf).strip()) for buf in raw)
    return [s for s in segments if s]


def _shell_head_word(segment: str) -> str:
    """Command name of a segment, skipping leading ``VAR=value`` assignments."""
    words = _split_shell_words(segment)
    while words and re.match(r"^[A-Za-z_]\w*=", words[0]):
        words.pop(0)
    return _shell_basename(words[0] if words else "")


def _clean_shell_segment(segment: str) -> str:
    """Drop redirections (``> file``, ``2>&1``) from a segment."""
    words = _split_shell_words(segment)
    out: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        if re.match(r"^\d*(?:>>?|<)$", word):
            i += 2
        elif re.match(r"^\d*(?:>&|<&)\d+$", word):
            i += 1
        else:
            out.append(word)
            i += 1
    return " ".join(out).strip()


def _is_shell_boundary_echo(segment: str) -> bool:
    words = _split_shell_words(segment)
    if _shell_basename(words[0] if words else "") != "echo":
        return False
    return bool(re.search(r"-{2,}|_exit=|(?:^|\s|=)\$[?{]|PIPESTATUS", " ".join(words[1:])))


def summarize_shell_command(command: str) -> str:
    """Compact shell wrapper/plumbing for display while preserving raw command elsewhere."""
    original = _oneline(command)
    if not original:
        return ""
    segments = _split_shell_compound(original)
    if len(segments) <= 1:
        return _clean_shell_segment(segments[0] if segments else original) or original
    core: list[str] = []
    for segment in segments:
        cleaned = _clean_shell_segment(segment)
        if cleaned and _shell_head_word(cleaned) not in _SHELL_SILENT_HEADS and not _is_shell_boundary_echo(cleaned):
            core.append(cleaned)
    if not core:
        return original
    count = len(core) - 1
    return core[0] if not count else f"{core[0]} + {count} {'command' if count == 1 else 'commands'}"


def _read_file_line_label(args: dict) -> str:
    offset, limit = args.get("offset"), args.get("limit")
    if not isinstance(offset, int) or offset <= 0:
        return ""
    return f"L{offset}-{offset + limit - 1}" if isinstance(limit, int) and limit > 1 else f"L{offset}"


def redact_browser_typed_text_for_display(value: Any, typed_text: Any) -> Any:
    """Replace every occurrence of a secret-looking browser_type value with its redacted form.

    Backends echo the attempted input in error strings/metadata, so it is swapped before
    reaching logs, callbacks, the model, or chat history. Forced regardless of
    ``security.redact_secrets``: a leaked typed credential is a security boundary.
    """
    needle = "" if typed_text is None else str(typed_text)
    redacted = redact_sensitive_text(needle, force=True) if needle else needle
    if redacted == needle:
        return value
    if isinstance(value, str):
        return value.replace(needle, redacted)
    if isinstance(value, dict):
        return {key: redact_browser_typed_text_for_display(item, typed_text) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_browser_typed_text_for_display(item, typed_text) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_browser_typed_text_for_display(item, typed_text) for item in value)
    return value


def redact_tool_args_for_display(tool_name: str, args: dict | None) -> dict | None:
    """Return a copy of tool args safe for logs/progress UI (masks ``browser_type`` secrets)."""
    if not isinstance(args, dict):
        return args
    if tool_name == "browser_type" and isinstance(args.get("text"), str):
        return {**args, "text": redact_sensitive_text(args["text"], force=True)}
    return args


def _delegate_task_goals(tasks: Any, *, per_goal_len: int) -> list[str]:
    """One truncated goal string per dict task (``?`` when missing)."""
    if not isinstance(tasks, list):
        return []
    raw_goals = (task.get("goal") for task in tasks if isinstance(task, dict))
    return [_truncate_preview(("?" if g is None else _oneline(str(g))) or "?", per_goal_len) for g in raw_goals]


def _browser_exec_step_label(args: dict, max_chars: int = 80) -> str | None:
    """User-friendly step label from browser_exec code's leading comment."""
    first = str(args.get("code", "") or "").strip().split("\n", 1)[0].strip()
    label = first.lstrip("#").strip() if first.startswith("#") else ""
    if not label:
        return None
    return label[: max_chars - 1] + "…" if len(label) > max_chars else label


_PRIMARY_ARGS = {
    "terminal": "command", "web_search": "query", "web_extract": "urls", "read_file": "path",
    "write_file": "path", "patch": "path", "search_files": "pattern", "browser_navigate": "url",
    "browser_click": "ref", "browser_type": "text", "image_generate": "prompt", "text_to_speech": "text",
    "vision_analyze": "question", "skill_view": "name", "skills_list": "category", "cronjob_manage": "action",
    "execute_code": "code", "browser_exec": "code", "delegate_task": "goal", "clarify": "question",
    "skill_manage": "name",
}


_FALLBACK_PREVIEW_KEYS = ("query", "text", "command", "path", "name", "prompt", "code", "goal")


def _delegate_action_preview(args: dict) -> str | None:
    """Shared ``list/steer/stop <id>`` preview for delegate_task, or None for spawn calls."""
    action = str(args.get("action") or "").strip().lower()
    if action in ("list", "steer", "stop"):
        return f"{action} {str(args.get('subagent_id') or '').strip()}".strip()
    return None


def _preview_browser_exec(args: dict, max_len: int) -> str | None:
    label = _browser_exec_step_label(args)
    if label is not None:
        return _truncate_preview(label, max_len)
    return _truncate_preview(_oneline(str(args.get("code", "") or "")), max_len) or None


def _preview_delegate_task(args: dict, max_len: int) -> str | None:
    action_preview = _delegate_action_preview(args)
    tasks = args.get("tasks")
    if action_preview is not None:
        return _truncate_preview(action_preview, max_len)
    if tasks and isinstance(tasks, list):
        goals = _delegate_task_goals(tasks, per_goal_len=40)
        preview = f"{len(goals)} tasks: " + " | ".join(goals) if goals else f"{len(tasks)} parallel tasks"
        return _truncate_preview(preview, max_len)
    goal = args.get("goal", "")
    return None if goal is None else _truncate_preview(_oneline(str(goal)), max_len) or None


def _preview_process_manage(args: dict, _max_len: int) -> str | None:
    action, sid, data, timeout_val = (args.get(k) for k in ("action", "session_id", "data", "timeout"))
    parts = [str(action) if action else "", str(sid)[:16] if sid else "",
             f'"{_oneline(str(data)[:20])}"' if data else "", f"{timeout_val}s" if timeout_val and action == "wait" else ""]
    return " ".join(p for p in parts if p) or None


def _preview_todo_list(args: dict, _max_len: int) -> str:
    todos_arg = args.get("todos")
    verb = "updating" if args.get("merge", False) else "planning"
    return "reading task list" if todos_arg is None else f"{verb} {len(todos_arg)} task(s)"


def _preview_shell(key: str):
    def _build(args: dict, max_len: int) -> str | None:
        command = args.get(key)
        return None if command is None else _truncate_preview(summarize_shell_command(str(command)), max_len) or None
    return _build


def _preview_read_file(args: dict, max_len: int) -> str | None:
    path = args.get("path") or args.get("file") or args.get("filepath")
    label = (Path(str(path).replace("\\", "/")).name or str(path)) if path is not None else None
    return None if label is None else _truncate_preview(f"{label} {_read_file_line_label(args)}".strip(), max_len) or None


def _preview_memory(args: dict, _max_len: int) -> str:
    action, target = args.get("action", ""), args.get("target", "")
    if action == "add":
        return f"+{target}: \"{_clip(_oneline(args.get('content', '')), 25)}\""
    if action in ("replace", "remove"):
        old = _oneline(args.get("old_text") or "") or "<missing old_text>"
        return f"{'~' if action == 'replace' else '-'}{target}: \"{old[:20]}\""
    return action


def _preview_send_message(args: dict, _max_len: int) -> str:
    return f"to {args.get('target', '?')}: \"{_tail_trunc(_oneline(args.get('message', '')), 20)}\""


def _preview_skill_view(args: dict, max_len: int) -> str | None:
    name = _oneline(str(args.get("name") or ""))
    file_path = args.get("file_path")
    label = (f"{name} → {_oneline(str(file_path))}" if name else _oneline(str(file_path))) if file_path else name
    return _truncate_preview(label, max_len) or None


_PREVIEW_BUILDERS = {
    "browser_exec": _preview_browser_exec, "delegate_task": _preview_delegate_task,
    "process_manage": _preview_process_manage, "todo_list": _preview_todo_list,
    "terminal": _preview_shell("command"), "execute_code": _preview_shell("code"),
    "read_file": _preview_read_file, "memory": _preview_memory, "send_message": _preview_send_message,
    "skill_view": _preview_skill_view,
    "session_search": lambda args, _m: f"recall: \"{_clip(_oneline(args.get('query', '')), 25)}\"",
}


def build_tool_preview(tool_name: str, args: dict, max_len: int | None = None) -> str | None:
    """Build a short preview of a tool call's primary argument for display.

    *max_len* ``None`` defers to the global ``_tool_preview_max_len``; ``0`` means unlimited.
    """
    if max_len is None:
        max_len = _tool_preview_max_len
    if not args:
        return None
    args = redact_tool_args_for_display(tool_name, args) or args
    builder = _PREVIEW_BUILDERS.get(tool_name)
    if builder is not None:
        return builder(args, max_len)
    key = _PRIMARY_ARGS.get(tool_name) or next((k for k in _FALLBACK_PREVIEW_KEYS if k in args), None)
    if not key or key not in args:
        return None
    value = args[key]
    preview = _oneline(str((value[0] if value else "") if isinstance(value, list) else value))
    return _tail_trunc(preview, max_len) if preview else None


_ERROR_SUFFIX_MAX_LEN = 48


def _trim_error(msg: str) -> str:
    """Shrink an error message for inline display (long 'File not found' paths -> filename)."""
    msg = msg.strip()
    if "File not found:" in msg:
        tail = msg.partition("File not found:")[2].strip()
        if "/" in tail:
            msg = f"File not found: {tail.rsplit('/', 1)[-1]}"
    return _tail_trunc(msg, _ERROR_SUFFIX_MAX_LEN)


def _detect_tool_failure(tool_name: str, result: str | None) -> tuple[bool, str]:
    """Return ``(is_failure, suffix)`` for a tool result, e.g. ``(True, " [exit 1]")``."""
    if result is None or file_mutation_result_landed(tool_name, result):
        return False, ""
    data = safe_json_loads(result)

    if tool_name == "terminal":
        exit_code = data.get("exit_code") if isinstance(data, dict) else None
        if exit_code is None or exit_code == 0:
            return False, ""
        err_msg = data.get("error")
        return True, f" [{_trim_error(str(err_msg))}]" if err_msg else f" [exit {exit_code}]"

    if isinstance(data, dict):
        failed = data.get("success") is False
        if tool_name == "memory" and failed and "exceed the limit" in data.get("error", ""):
            return True, " [full]"
        err = data.get("error") or data.get("message")
        if err and (failed or "error" in data):
            return True, f" [{_trim_error(str(err))}]"
    if isinstance(result, str) and (
        '"error"' in result[:500].lower() or '"failed"' in result[:500].lower() or result.startswith("Error")
    ):
        return True, " [error]"
    return False, ""


def format_tool_completion(tool_name: str, args: dict, duration: float, result: str | None = None) -> str:
    """Plain completion metadata; frontend clients own visual rendering."""
    failed, error = _detect_tool_failure(tool_name, result)
    return f"{tool_name} failed: {error}" if failed else f"{tool_name} completed in {duration:.1f}s"
