# Engine health review

Reviewed the current working tree on 2026-10-08, excluding Git history. This review updates the earlier frontend cleanup audit and its file inventory.

## Findings and repairs

The legacy product name was absent from current file names and contents, including hidden and ignored project files. The scan also inspected common Unicode encodings and ZIP entries. No branding replacements were needed.

The backend has useful boundaries between agent orchestration, configuration/authentication, tool execution, plugins, session storage, and scheduling. The callback interfaces provide an embedding surface for a future UI. Several modules exceed 3,000 lines, including the auxiliary client and compression implementation; splitting those by responsibility would improve maintenance. Import reachability alone cannot prove that a plugin or skill is unused.

Fixed concrete failures exposed by the review:

- Configuration diagnostics called deleted frontend color helpers. Diagnostics now return plain text.
- Skills hub search used `os` without importing it.
- Custom model catalog caching imported a deleted terminal picker type. A small backend catalog type now preserves authoritative empty results and caching without that dependency.
- Configuration loading referenced an absent migration module. Current-schema configuration works; older schemas produce an explicit warning and retain their stored version, rather than claiming an upgrade occurred.
- Platform toolset validation referenced a deleted module. A backend validator now checks names, selection types, and platform restrictions without changing configuration.
- An optional skill loaded helper scripts with `exec` in the caller's namespace, potentially triggering their command entrypoints. Helpers now load under a separate module namespace with explicit function bindings.

## Verification

- All **16 engine regression tests passed** on Python **3.12.14**. Tests cover initialization, direct providers, pricing, audio/vendor configuration, request contexts, session persistence, approvals, OAuth callbacks, delegation, and a complete model/tool/model conversation with stable system messages.
- Actual file writing/reading, terminal execution, native plugin registration/dispatch, scheduled script execution, configuration roundtrips, model catalog caching, and toolset validation passed. Windows terminal checks required execution outside the filesystem sandbox; profiles and files remained isolated in temporary directories.
- **628 backend modules imported successfully**, with no import failures, using core test dependencies and the MCP extra. External network calls and lazy installs were disabled during the import audit.
- Ruff checks for undefined names, invalid exports, and unbound local names (`F821`, `F822`, `F823`) passed across the project.
- All Python source files parsed and compiled; JSON, TOML, and YAML configuration files parsed successfully.
- An editable package build/install succeeded. `uv lock --check --offline` confirmed the dependency lock agrees with project metadata.

Run the retained regressions with `python scripts/verify_engine_cleanup.py` after installing dependencies on Python 3.11–3.13. Tests isolate `ARKOS_HOME` and `Path.home`, disable dependency installation, and block external socket connections while allowing local loopback IPC. Validation used OpenAI 2.24.0, Pydantic 2.13.4, and a focused dependency environment; it was not a full installation of every optional extra from the lockfile.

## Remaining limits

This is evidence that the tested engine paths work, not a guarantee that every integration is error-free. Live provider APIs, all third-party plugins, native builds, and long-running production schedules were not tested. The slim checkout does not contain the original complete test suite.

Older configuration migrations need an explicit implementation before supporting automatic upgrades. Removed messaging adapters, portable plugin loading, and host platform actions remain unavailable unless an embedding host supplies their implementations. The inventory lists remaining absent local modules; many references are guarded fallbacks or optional integration boundaries, and successful imports do not exercise every such function.

The earlier cleanup audit records its original verification state. This document is the current health assessment. Git history is unchanged; the engine cleanup and these repairs are intended for the existing `engine-only` branch.
