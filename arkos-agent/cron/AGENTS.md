# cron/ — scheduled jobs

Applies on top of the root `AGENTS.md`.

## Cron

`cron/jobs.py` (job store) + `cron/scheduler.py` (tick loop; `scheduler_*.py` siblings). Agents
schedule via the `cronjob` tool; users via `arkos cron list|add|edit|pause|resume|run|remove` or
`/cron`. Schedules: duration (`"30m"`, `"2h"`, `"1d"`), "every" phrase (`"every 2h"`, `"every monday
9am"`), 5-field cron (`"0 9 * * *"`), ISO one-shot (`"2026-06-01T09:00:00Z"`). Per-job fields:
`skills`, `model`/`provider` overrides, `script` (pre-run data-collection script whose stdout is
injected into the prompt; `no_agent=True` makes the script the whole job), `context_from` (chain job
A's last output into job B's prompt), `workdir` (run with that directory's `AGENTS.md`/`CLAUDE.md`
loaded), multi-platform delivery.

Hardening invariants — each guards a real failure; don't weaken without answering for it:
- **3-minute hard interrupt** on cron sessions: runaway loops cannot monopolise the scheduler.
- Catch-up window = half the period, clamped to 120s–2h; 120s grace for missed one-shots.
- File lock `~/.arkos/cron/.tick.lock` prevents duplicate ticks across processes.
- Cron sessions pass `skip_memory=True`; memory providers intentionally do not run during cron.
- Deliveries are **not mirrored** into the target gateway session — they land in their own cron
  session with a header/footer frame so the main conversation's role alternation stays intact.
- The cron ticker runs in the desktop-spawned backend when `ARKOS_DESKTOP=1` — that env var means
  "spawned by the app", not "a GUI is watching" (root: capability is a property of the session).
- Background `delegate_task` is process-local; work that must survive restarts is a cron job or a
  `terminal(background=True, notify_on_complete=True)` process.

## Tests

`tests/cron/`. Schedule parsing
and catch-up windows are pure functions — test them as data. Never assert on the verb list or
toolset size (root: no change-detectors). Time-based tests use loose bounds (≥ 2s) and event sync.
(Kanban tests `test_kanban*.py` removed with the subsystem.)

*Part of Arkos, an AI agent engine.*
