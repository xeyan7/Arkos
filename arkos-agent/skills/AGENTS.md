# skills/ + optional-skills/ — bundled skills, authoring standards, curator

Applies on top of the root `AGENTS.md`. (Long-form site guides are not shipped in this slim distribution.)

## Two surfaces

- **`skills/`** — built-in, loadable by default, organised by category (`skills/github/`, `skills/mlops/`).
- **`optional-skills/`** — heavier/niche skills shipped but NOT active; installed via
  `arkos skills install official/<category>/<skill>` (adapter `tools/skills_hub_official.py`
  `OptionalSkillSource`). Categories: `autonomous-ai-agents, blockchain, communication, creative,
  devops, email, health, mcp, migration, mlops, productivity, research, security, web-development`.

Reviewing a skill PR: check the target directory — heavy-dep or niche skills go to `optional-skills/`.

## SKILL.md frontmatter

`name`, `description`, `version`, `author`, `license`, `platforms` (OS gate: `[macos]`,
`[linux, macos]`, ...), `metadata.arkos.tags`, `metadata.arkos.category`,
`metadata.arkos.related_skills`, `metadata.arkos.config` (config.yaml settings the skill needs —
stored under `skills.config.<key>`, prompted during setup, injected at load). Top-level `tags:` /
`category:` are accepted and mirrored from `metadata.arkos.*` by the loader.

## Authoring standards (HARDLINE — enforced by `tests/skills/test_authoring_standards.py` in a full checkout)

Every new or modernised skill — bundled, optional, or contributed — meets all of these before merge:

1. **`description` ≤ 60 chars, one sentence, ends with a period.** Long descriptions bloat listings
   and dilute attention when many skills load. State the capability, not the implementation; no
   marketing words ("powerful", "comprehensive", "seamless", "advanced"); don't repeat the name.
   Check: `len(re.search(r'^description: (.*)$', text, re.M).group(1)) <= 60`.
2. **Prose references native agent tools or the MCP servers the skill expects, in backticks**
   (`terminal`, `web_extract`, `read_file`, `patch`, `search_files`, `vision_analyze`,
   `browser_navigate`, `delegate_task`). Never name shell utilities the agent has wrapped: `grep` →
   `search_files`, `cat`/`head`/`tail` → `read_file`, `sed`/`awk` → `patch`, `find`/`ls` →
   `search_files target='files'`. MCP dependencies are named with setup in `## Prerequisites`.
   Third-party CLIs and pipelines are fine inside script files, not as the headline surface.
3. **`platforms:` gating is audited against actual script imports.** POSIX-only primitives
   (`fcntl`, `termios`, `os.setsid`, `os.kill(pid, 0)`, `/proc`, hardcoded `/tmp`, `signal.SIGKILL`,
   bash heredocs, `osascript`, `apt`, `systemctl`) require a platform declaration. Fix cross-platform
   first (`tempfile.gettempdir`, `pathlib.Path`, `psutil.pid_exists`, Python filtering instead of
   `grep`); gate narrower only when the dependency is genuinely platform-bound.
4. **`author` credits the human first.** External contributor's real name + GitHub handle first,
 "Arkos" second. A commit authored as "Arkos" (they drafted with the agent) is replaced
   with the human's name — credit the human, not the tool.
5. **Modern section order:** `# <Skill> Skill`, 2–3 sentence intro (what it does and doesn't),
   `## When to Use`, `## Prerequisites`, `## How to Run`, `## Quick Reference`, `## Procedure`,
   `## Pitfalls`, `## Verification`. ~200 lines for a complex skill, ~100 simple. Cut intro fluff,
   marketing prose, and env-var re-explanations already in Prerequisites.
6. **`scripts/`, `references/`, `templates/`.** Don't make the model inline-write parsers or
   non-trivial logic every call — ship a helper script and reference it by skill-relative path.
7. **Tests at `tests/skills/test_<skill>_skill.py`**, stdlib + pytest + `unittest.mock` only, no
   live network. Run `pytest tests/skills/test_<skill>_skill.py -q` from a full checkout (suite not shipped slim).
8. **`.env.example` additions sit in a clearly delimited block.** Contributor copies of the file are
   usually stale; edits outside the skill's own block are dropped during salvage.

No `offset`/`limit` pagination on skill-loading tools — the agent must read a skill fully (root).
The salvage/modernisation checklist for external skill PRs is `references/new-skill-pr-salvage.md`
in the `arkos-agent-dev` skill.

## Curator (skill lifecycle)

Background maintenance that tracks usage on agent-created skills and auto-archives stale ones;
archives go to `~/.arkos/skills/.archive/` and are restorable. Core `agent/curator.py` (review
loop, auto-transitions, LLM review prompt) + `agent/curator_backup.py` (pre-run tar.gz snapshots);
CLI `arkos curator status|run|...` (engine build: `arkos_cli/curator.py` entry deleted,
backend `agent/curator.py` remains); telemetry `tools/skill_usage.py` owns `~/.arkos/skills/.usage.json`
(`use_count`, `view_count`, `patch_count`, `last_activity_at`, `state` active/stale/archived,
`pinned`). Config `curator:` — `enabled, interval_hours, min_idle_hours, stale_after_days,
archive_after_days, backup.*`; its LLM calls route through `auxiliary` (`agent/AGENTS.md`).

Invariants: touches only `created_by: "agent"` skills (bundled + hub-installed are off-limits);
never deletes — archive is the maximum; pinned skills are exempt from every auto-transition and
the LLM review; `skill_manage(action="delete")` refuses pinned skills while patch/edit/write_file/
remove_file still work so the agent can keep improving them.

*Part of Arkos, an AI agent engine.*
