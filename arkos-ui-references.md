# Arkos — competitor & UI reference research

Researched: 2026-10-19. Scope: understand Arkos (desktop workspace for coding agents), find similar
apps, and collect UI references worth studying. **No UI was added or changed.**

Method note: the built-in `web_search` tool is misconfigured in this session (its Messages API
endpoint at `http://127.0.0.1:3425/v1/messages` refuses connections), so discovery ran through
direct page fetches, `raw.githubusercontent.com` READMEs, and RSS search endpoints. Several domains
(openai.com, cursor.com, warp.dev, raycast.com, github.com HTML, block.xyz, graphite.dev) were not
reachable from this machine, so a few entries below rest on product news and prior knowledge rather
than a page I opened today. Each entry is marked:

- **[V]** = verified today by fetching the product page, docs, or repository README.
- **[N]** = seen in October 2026 news headlines/queries, not opened directly.
- **[K]** = well-known product from prior knowledge; URL is the canonical one, details not re-verified.

I could not view the existing PNG screenshots (`arkos-*.png`) — the current model has no image
input — so the "what Arkos is" section below is reconstructed from the source tree, not from pixels.

---

## 1. What Arkos is (my read of the codebase)

**One line:** a local-first desktop workbench that runs coding-agent CLIs (Codex, Claude Code,
Cursor, Antigravity, Grok, Droid, OpenCode, Pi, Devin — plus the private Arkos Python engine) inside
a single project/thread workspace, with review, terminal, browser, editor, git and PR tooling next to
the conversation, and deep theming control.

### Product model

| Layer | What it is in the code |
| --- | --- |
| Project | Repository context, settings, per-project appearance, worktree policy |
| Thread | Conversation + state + files + history; pins, snooze, archive, recap, notes, side chats, forks, handoffs, subagent threads |
| Provider session | A locally installed, locally authenticated agent runtime (9 integrations listed in the README) |
| Environment | Local checkout or managed git worktree; group/studio/scratch workspaces |
| Workspace tools | Diff/Changes, Terminal, Browser, Explorer/File editor, Git, PR, Side chats, iOS Simulator |

### Surfaces that exist today (routes and dock panes)

- App rail + collapsible panel: Home, Inbox, Spaces, Kanban, Tasks, Pull requests, Automations,
  Studio/Hubs, Settings — order and visibility user-configurable (`appRail.logic.ts`).
- Chat surface: single and split panes, per-pane thread tabs, transcript with work log, tool-call
  groups, thinking, subagent strips, queued turns, plan cards, pending approvals/user input.
- Right dock panes: Diff, Terminal, Browser, Explorer, File, Side chats, Git, Pull request,
  iOS Simulator — with launcher order Diff → Terminal → Browser → Explorer → Side chats → … .
- Kanban with an "Attention" and a "Classic" view; card states derived from work ("Done",
  "Awaiting you"), "Send as goal", move-to, archive, pin.
- Inbox, Tasks, Pull requests (with auto-fix hints), Automations (recurring runs), Usage & limits
  (rate-limit meters, reset credits), AppSnap (window snap), Computer use, Devices.
- Settings: Personal / Integrations / Coding / System / Archived groups — General, Profile,
  Appearance, Notifications, Chat behavior, Keybindings, Usage & limits, AppSnap, Computer use,
  MCP connections, Agent providers, Models & writing, Agent skills, Managed worktrees, System tools,
  Archived threads.

### How it runs

- `apps/desktop` — Electron 43 main process. Supervises the backend, custom title bar, window
  material/glass, native menus, browser manager (`betterwright`), computer-use driver host (CUA),
  AppSnap, updater (electron-updater), crash/renderer recovery.
- `apps/server` (`@arkos/cli`) — Bun + Effect server. SQLite via `@effect/sql-sqlite-bun`, WebSocket
  RPC plus snapshot/live streams, `node-pty` terminals, git + managed worktrees, automations,
  external MCP, pull requests, GitHub inbox, browser automation, device helper, diagnostics,
  checkpointing, voice transcription. Providers are driven through the Agent Client Protocol SDK,
  the Claude Agent SDK, the OpenCode SDK, and Pi's agent core.
- `apps/web` — React 19, TanStack Router/Query/Virtual, Tailwind v4, Base UI + shadcn
  (style `base-rhea`), xterm, Lexical, `@pierre/diffs`, Legend List, Zustand, tabler icons.
- `packages/contracts`, `packages/shared` — wire contracts and shared logic.
- `E:\app\arkos-agent` — the separate private Python engine (memory, skills, plugins, cron,
  subagents, terminal/browser tools) that the desktop can bridge to.

### Design system already in place

- Token-driven themes with **28 theme packs** (Arkos, Absolutely, Ayu, Catppuccin, Codex, Dracula,
  Everforest, GitHub, Gruvbox, Linear, Lobster, Material, Matrix, Monokai, Night Owl, Nord, Notion,
  One, Oscurange, Proof, Raycast, Rose Pine, Sentry, Solarized, Temple, Tokyo Night, Vercel,
  VS Code Plus) — several named after the very products in section 5.
- Light/dark, typography scale that follows Settings, density preferences, radius scale, glass /
  window material tokens, sidebar chip surfaces, stepped 20 fps spinners synced to a shared
  animation timeline, `prefers-reduced-motion`-aware disclosure motion, motion perf test suites.

**Implication for references:** Arkos is not a blank slate. It is already *broader* than most peers
(kanban + inbox + tasks + PRs + automations + device preview + 9 providers + theme packs). The
useful references are therefore about **craft, hierarchy, and one-surface-at-a-time excellence**,
not about adding more features.

---

## 2. Tier 1 — closest peers (agent workbenches)

### 2.1 Conductor — `conductor.build` **[V]**

Closest competitor, and the most useful UI document in the category: their public changelog is a
running list of exactly the interaction problems Arkos will hit.

- Desktop (macOS) + iOS + API; runs Claude Code, Codex, Cursor and OpenCode as first-party agents;
  local workspaces plus cloud microVM sandboxes; now **multiplayer** (share a workspace link ⌘⇧C,
  presence, follow work).
- Sidebar: Pinned section, My workspaces, status-grouped and collapsible sections, drag reorder that
  syncs across devices, per-workspace hover metadata (repository), matrix-style status marks
  (idle / running / attention / error / PR checks / merged), ⌘1–9 jumps that skip collapsed sections.
- Tabs everywhere: desktop tabs per workspace, chat tabs, PR tabs, browser tabs, terminal tabs.
- Chat craft worth copying: agent thinking groups, tool-call groups, queued messages that render
  faded "until the agent reads them", stop button becomes primary while running and flips back to
  send when you type, plan approval surviving restart, inline "Run" buttons on bash snippets,
  inline media players, "Background Task" rows, ⌘F finds matches inside thinking and expands the
  collapsed group.
- Review: Changes panel with path filter, "mark file as viewed" persisting across restarts,
  loading bar on diff refresh, stacked-PR stack listed inside the Changes tab, inline comments,
  suggested changes rendered as diffs, clicking a line number opens a comment.
- PR view: one status card (branch, review, checks, merge) with description and activity below;
  nested replies to review comments; "add unresolved comments to chat"; re-run failed checks.
- Extras: Routines (hourly/daily/weekdays/weekly, GitHub trigger filters by label/author/base
  branch), port forwarding with process names, CSV as table / JSON collapsible previews, Mermaid,
  voice mode with live mic level, MCP popover showing tool counts per server, context-usage popover
  per account, resource-usage inspector, "Pokes".

**Study:** sidebar information architecture, status semantics, queued-message affordance, stacked-PR
handling, routine authoring UI, diff "viewed" model.

### 2.2 Berd (Block) — `github.com/block/berd` **[V]**

Open-source desktop app for working with AI agents: Tauri 2 + React 19, talking to the upstream
Goose backend over ACP WebSocket, with an optional companion CLI and a **design-system check in
`just check`** (Biome, design-system, i18n, contract, type checks). Block also published a design
write-up, "Designing AI with character" (`block.xyz/inside/…`, page not reachable from here **[N]**).

**Study:** closest architectural cousin (desktop shell + ACP agent backend), how a team enforces a
design system in CI, and the "character" argument — how an agent app earns personality without
becoming a toy.

### 2.3 Claude Code desktop app — `claude.com/product/claude-code`, docs at `code.claude.com/docs` **[V]**

Anthropic's own GUI for Claude Code. The docs tree shows the 2026 shape of the product: desktop
quickstart/reference, Linux beta, Windows via WSL, **scheduled tasks**, an **iOS simulator (beta)**
panel, local code review, "Ultrareview", computer use, Remote Control, mobile, Slack, VS Code and
JetBrains. VentureBeat's April 2026 hands-on describes a redesigned desktop app plus "Routines",
and an October 2026 item describes nested sessions and saved environments **[N]**.

**Study:** how the reference implementation of one agent presents sessions, scheduled runs, a device
preview, and review — directly comparable to Arkos's Automations + Device + Diff panes.

### 2.4 OpenAI Codex app — `openai.com/codex` **[N]/[K]**

Desktop app for the Codex agent; reached Windows in March 2026; April 2026 coverage describes Codex
controlling the desktop, which lines up with Arkos's Computer use surface. Page not reachable from
this machine; verify current UI before borrowing specifics.

### 2.5 GitHub Copilot app — `github.blog` **[N]**

"Agent-native desktop experience" announced June 2026, positioned as managing multiple agents.
**Study:** how GitHub maps issues → agent sessions → PRs, and how they present checks/CI state —
the same verbs Arkos already has in Kanban, Tasks and Pull requests.

### 2.6 Cursor — `cursor.com` **[N]/[K]**

Multi-agent IDE; 2026 additions include an iOS app for running agents remotely. **Study:** the agent
list/detail model, background agents, inline diff review, and how a large feature set stays under one
command palette. (Cursor's own UI is a common "feel" benchmark — see also 2.6.1.)

### 2.7 OpenCode v2 — `opencode.ai` **[V]**

Open-source agent with terminal, IDE and **desktop** front ends; v2 site advertises multi-session
parallel agents on one project, share links per session, 75+ providers. **Study:** session list and
share/permalinks, provider-model picker breadth, how a CLI-first product designs its GUI without
losing power-user muscle memory.

### 2.8 Nimbalyst (formerly Crystal) — `nimbalyst.com` **[V]**

Crystal (the multi-session Claude Code manager) was deprecated in February 2026 and replaced by
Nimbalyst: a "visual workspace for agents, tasks, docs, wiki, diagrams, and code", Electron,
multi-editor (code/markdown/spreadsheet/diagram/visual docs), streaming edits into open editors,
worktree isolation, plus an agent-written wiki and a shared multiplayer wiki for teams.

**Study:** the multi-editor canvas idea (Arkos stops at Explorer/File), wiki-as-shared-memory, and
how they teach "think clearly when overwhelmed by agents" in the empty states and onboarding.

### 2.9 Delta (Zed Industries) — `delta.dev` **[V]**

New (2026, beta) "multiplayer environment for coding with agents, powered by DeltaDB" from the Zed
team: conversations and code live in one place, every change anchored to the reasoning that produced
it. **Study:** anchoring/diff provenance — "why does this line exist" as a first-class UI object —
and multiplayer editing of agent threads.

### 2.10 Zed — `zed.dev` **[V]**

Editor with an agent panel, multibuffer editing, and famously careful performance/motion work.
**Study:** agent panel layout, multibuffer diff editing (edit many files in one surface), and their
keymap/command-palette conventions.

### 2.11 Google Antigravity 2.0 — **[N]**

Desktop app + CLI, relaunched at I/O 2026. **Study:** the manager/editor/agent-view split and
artifact review, if you can run it.

### 2.12 Devin Desktop — **[N]**

Cognition's desktop client for Devin. **Study:** long-running autonomous session presentation —
how a task that runs for hours is summarized when you come back.

### 2.13 BAND desktop — **[N]**

October 2026 launch; desktop app for developer collaboration and control of multiple AI coding
agents across teams (coverage: SiliconANGLE, DevOps.com, citybiz). **Study:** team-scale agent
management — closest thing to a "multiplayer agent workspace" besides Conductor.

### 2.14 Vibe Kanban — `vibekanban.com`, `github.com/BloopAI/vibe-kanban` **[V]**

Sunsetting (open-source, community-maintained) but still the cleanest reference for the
**plan → prompt → review** loop: kanban issues with sub-issues, workspaces that give each agent a
branch + terminal + dev server, inline diff comments sent straight back to the agent, built-in
browser with devtools/inspect/device emulation, PR creation and merge, 10+ agents. **Study:** board
card anatomy, workspace headers, the review-comment-to-agent loop, and browser-in-app ergonomics.

### 2.15 Claude Squad — `github.com/smtg-ai/claude-squad` **[V]**

TUI that manages multiple agents in tmux sessions with git worktrees; preview tab ↔ diff tab per
session; commit/checkout/resume actions. **Study:** extreme-compact information design for
many parallel agents, and the paused/checked-out session state model.

### 2.16 Omnara — `omnara.com`, `github.com/omnara-ai/omnara` **[V]**

Evolved into an open-source managed agent platform (Docker, Postgres event log, workers, machines,
sandboxes, Slack/Discord/GitHub triggers, permissions per tool, cron triggers). Not a UI peer, but
**study** its event-stream/approval model and its dashboard's agent timeline if you plan deeper
automation and observability in Arkos.

---

## 3. Tier 2 — adjacent tools, by the surface they inform

| Surface in Arkos | References to study | Why |
| --- | --- | --- |
| Terminal pane | **Warp** `warp.dev` **[K]** (block-based terminal, agent mode), **Ghostty** `ghostty.org` **[K]** (native speed, minimal chrome, great defaults), **iTerm2**, **Tabby**, **Wave Terminal**, VS Code terminal tabs **[K]** | Block grouping, command output affordances, tab/split handling, ligature & font settings; what "terminal chrome" should not do |
| Editor / file pane | **Zed** **[V]**, **VS Code** (quick open, breadcrumbs, editor groups), **JetBrains** (structure view), **Lexical** playground | Multibuffer diff editing, breadcrumb hierarchy, minimap vs none, dirty-state language |
| Diff & review | **GitHub PR "Files changed"** **[K]**, **Graphite** `graphite.dev` **[K]**, **Pierre** `pierre.computer` **[K]** (already a dependency as `@pierre/diffs`), **CodeRabbit**, **Greptile**, **Reviewable** **[K]** | File tree + viewed checkboxes, stacked diffs, suggestion blocks, keyboard navigation between changes, comment threading |
| Agent activity / traces | **LangSmith** `smith.langchain.com` **[K]**, **Langfuse** `langfuse.com` **[K]**, **Braintrust**, **Helicone**, **W&B Weave** **[K]**, **OpenTelemetry GenAI conventions** | Tree/waterfall rendering of steps, token & cost attribution, collapsing noisy tool calls, run comparison |
| Kanban / tasks | **Vibe Kanban** **[V]**, **Linear** boards **[K]**, **Height** **[K]**, **Notion** databases, **GitHub Projects** **[K]** | Card anatomy, derived vs manual columns, WIP limits, drag affordances, keyboard move |
| Inbox / triage / notifications | **Linear Inbox** **[K]**, **GitHub notifications**, **Superhuman** **[K]**, **Slack Activity** | Read/unread semantics, snooze, grouping, "needs you" derivation, toast vs persistent inbox split |
| Automations / schedules | **Conductor Routines** **[V]**, **GitHub Actions** run history **[K]**, **Vercel Cron**, **n8n**, **Zapier** **[K]**, Claude Code **scheduled tasks** **[V]** | Trigger + filter builders, run history with diffs of outcome, failure policy surfacing |
| Usage, limits, billing | **Vercel usage**, **Stripe billing**, **OpenAI/Anthropic usage pages**, **Cursor usage** **[K]** | Meter design, reset countdowns, "credits" language, pace/projection charts |
| Browser + device preview | **Chrome DevTools device mode**, **Playwright Trace Viewer**, **Browserbase**, **Cursor's browser**, **Vibe Kanban's browser** **[K]/[V]** | Viewport chrome, inspect mode, console surface, screenshot annotation → agent loop |
| Computer use | **Claude computer use** **[V]**, **ChatGPT desktop control / Operator** **[N]**, **Arkos CUA driver** (in-repo) | Permission + kill-switch UX, live frame preview, "what is it doing now" narration |
| Voice input | **Wispr Flow**, **Granola**, **Superwhisper** **[K]**, Conductor voice mode **[V]** | Live level meters, transcript-before-send, dictation vs command modes |
| Multiplayer / presence | **Conductor multiplayer** **[V]**, **Delta** **[V]**, **Figma** cursors, **tldraw**, **Liveblocks** **[K]** | Presence, follow mode, shared cursors in code and chat, conflict affordances |
| Local-first state & sync | **Obsidian**, **Linear offline/sync states**, **Actual Budget** **[K]** | Sync/refresh indicators, "stale but usable" states, background refresh honesty |

---

## 4. Tier 3 — UI craft references (the "great UI" list)

### 4.1 Benchmark interfaces

| Reference | Link | What to steal |
| --- | --- | --- |
| Linear | `linear.app` **[V]** | Keyboard-first everything, ⌘K, restrained motion, sidebar hierarchy, issue-row density, opinionated empty states, the Linear Method as a writing model |
| Raycast | `raycast.com` **[K]** | Launcher chrome, command palette depth, extension store browsing, theme system, settings layout, "one input, many modes" |
| Vercel + Geist | `vercel.com`, `vercel.com/geist` **[K]** | Monochrome restraint, deployment/state vocabulary, typography and spacing discipline in a data-dense dashboard |
| GitHub | `github.com` **[K]** | PR review anatomy, checks UI, timeline events, notification triage, dark/light parity at scale |
| Sentry | `sentry.io` **[K]** | Issue detail density, breadcrumbs, trace waterfall, first-seen/regression chips |
| Stripe | `stripe.com`, dashboard, docs **[K]** | Tables and docs craft, error message tone, test-mode affordances |
| Notion | `notion.com` **[K]** | Sidebar + block editor, drag handles, database views, command palette |
| Arc / Dia | `arc.net`, `diabrowser.com` **[K]** | Sidebar-first browser, Spaces, split view, pinned vs ephemeral tabs (closest mental model to Arkos's rail + panel + split panes) |
| Things 3 | `culturedcode.com/things` **[K]** | Task hierarchy, delightful micro-interactions, calm empty states |
| Superhuman | `superhuman.com` **[K]** | Speed as a feature, inbox triage, keyboard-first onboarding |
| Height | `height.app` **[K]** | Task automation, inline editing, chat-like task views |
| Family | `family.co` **[K]** | Craft-level polish of small surfaces, onboarding |
| Granola | `granola.ai` **[K]** | Minimal capture surface, AI summary presentation, no-chrome aesthetic |
| Amie | `amie.so` **[K]** | Motion and personality in a productivity tool |
| Resend | `resend.com` **[K]** | Developer-tool marketing and dashboard aesthetics |
| Clerk | `clerk.com` **[K]** | Auth/onboarding component polish |
| Neon | `neon.tech` **[K]** | Data console design, branching metaphors (useful for worktrees!) |
| PostHog | `posthog.com` **[K]** | Dashboards, feature-flag UX, self-serve complexity management |
| Supabase | `supabase.com` **[K]** | Table editor, dense data UI, docs |
| tldraw / Excalidraw | `tldraw.dev`, `excalidraw.com` **[K]** | Infinite canvas, selection tools — if Kanban ever grows a canvas view |
| Obsidian | `obsidian.md` **[K]** | Local-first trust signals, plugin ecosystem UX |

### 4.2 Design-engineering craft (the people and primitives)

| Reference | Link | Why it matters for Arkos |
| --- | --- | --- |
| Emil Kowalski — Sonner, Vaul | `emilkowalski.com`, `sonner.emilkowalski.com` | Toast and drawer craft; his animation writing maps directly onto Arkos's disclosure motion and toasts |
| Rauno Freiberg | `rauno.me` | Interaction details, "invisible" polish, tooltip/popover behavior |
| Paco Coursey — cmdk | `cmdk.paco.me` | The command-menu primitive behind most good ⌘K surfaces |
| shadcn/ui | `ui.shadcn.com` | Arkos already uses it (style `base-rhea`); study registry/theme patterns for the theme-pack editor |
| Base UI | `base-ui.com` | Arkos's component base; check their newer primitives before hand-rolling |
| Radix | `radix-ui.com` | Accessibility primitives and docs style |
| Radix Colors / Tailwind v4 / OKLCH | `radix-ui.com/colors`, `tailwindcss.com` | Palette generation, semantic scales, wide-gamut color for theme packs |
| Motion (ex Framer Motion) | `motion.dev` | Layout/spring animation; compare with the current stepped-spinner + timeline-sync approach |
| tweakcn | `tweakcn.com` | Live shadcn theme editing — closest thing to Arkos's Theme Pack Editor |
| Refactoring UI | `refactoringui.com` | Hierarchy, spacing, color rules; good shared vocabulary for design review |
| Practical Typography | `practicaltypography.com` | Type scale discipline for the Settings-driven typography system |
| Apple HIG / Fluent 2 / Material 3 | `developer.apple.com/design`, `fluent2.microsoft.design`, `m3.material.io` | Native chrome expectations for macOS/Windows/Linux desktop apps |
| Mobbin, Refero, SaaSFrame, Godly, Land-book | `mobbin.com`, `refero.design`, `saasframe.io`, `godly.website`, `land-book.com` | Pattern galleries — fastest way to collect flows (onboarding, settings, empty states) before designing |
| Design Details podcast / Linear Method | `designdetails.fm`, `linear.app/method` | How strong teams justify UI decisions in writing |

---

## 5. Pattern → reference matrix (concrete)

| Arkos surface | Copy the pattern from | Specifically |
| --- | --- | --- |
| App rail + panel | Arc/Dia, Linear, VS Code activity bar | Rail items that are panels (Home/Spaces) vs routes (Kanban/Tasks/PRs); collapsed-panel header takeover is already handled by `AppShellTopStrip` |
| Thread rows | Linear issue rows, Superhuman, Conductor sidebar | Status marks, meta chips, hover actions, collapsed sections, ⌘1–9 with hidden-item skipping |
| Transcript / work log | Conductor, Claude Code, LangSmith | Thinking groups, tool-call grouping + collapse, queued-message fading, "background task" rows, find-in-thinking |
| Composer | Conductor, ChatGPT/Claude, Cursor, Slack | Slash-command menu, mention chips, model/trait pickers with search + favorites, plan-mode toggle, attachments tray, voice with level meter, one primary action that adapts |
| Diff pane | GitHub, Graphite, Pierre, Conductor | File tree with change markers, viewed state, per-file collapse, inline comments, suggestion rendering, next/prev change, loading bar on refresh |
| Terminal pane | Warp, Ghostty, VS Code | Blocks vs raw scrollback, tabs/splits, search, shell integration, link handling |
| Browser + device pane | Chrome DevTools, Vibe Kanban, Playwright trace | Device chrome, inspect mode, console, annotation → prompt |
| Kanban / Tasks | Vibe Kanban, Linear, Height | Card anatomy, derived columns, sub-tasks, "send as goal" affordance, keyboard move |
| Inbox | Linear Inbox, GitHub notifications | Unread/read, snooze with countdown, grouping by project, "why is this here" |
| Automations | Conductor Routines, GitHub Actions, Vercel Cron | Trigger + filter builder, next-run preview, run history with outcome, failure policy |
| Usage & limits | Vercel, Stripe, Cursor | Meters, pace/projection, reset countdowns, plan comparison |
| Settings | Raycast, VS Code, Linear | Grouped sidebar, search, per-section maturity badges (Arkos already has them), reset-to-defaults |
| Onboarding / empty states | Linear, Raycast, Things, Granola | One decision per screen, templates over blank pages, honest "what happens next" |
| Command palette | Raycast, Linear ⌘K, cmdk, VS Code | Scope switching (workspace vs global), recents, inline actions, result previews |
| Theming / appearance | Raycast themes, VS Code theme picker, tweakcn, Catppuccin | Live preview grid, per-theme variants, contrast warnings, import/export |
| Notifications | Sonner, Linear, GitHub | Stacking, promotion to inbox, do-not-disturb, per-source muting |

---

## 6. Theme-pack reality check

Arkos already ships 28 packs — including **Linear, Raycast, Vercel, Notion, GitHub, Codex, Sentry,
Material, Dracula, Gruvbox, Nord, Solarized, Tokyo Night, Catppuccin, Rose Pine, Everforest, Ayu,
Monokai, Night Owl**. That is the standard community palette set.

Gaps worth considering (as *research*, not implementation): **Kanagawa**, **Everblush**, **Melange**,
**Zenburn**, **Iceberg**, **Flexoki** (Steph Ango's system — excellent semantic-color reasoning),
**Radix Colors** scales, **OKLCH**-generated neutrals, and an accessibility-first high-contrast pair.
Study **Flexoki** (`stephango.com/flexoki`) and **Radix Colors** for how they justify semantic tokens
rather than hand-picking hex values.

---

## 7. Shortlist — study these ten first

1. **Conductor** — the live playbook for this exact product category (changelog is the syllabus).
2. **Berd (Block)** — the closest open-source architecture, plus a public design essay.
3. **Vibe Kanban** — plan/prompt/review IA you can still read in source before it fades.
4. **Linear** — the density, keyboard and motion benchmark.
5. **Raycast** — palette, settings and theming reference.
6. **Warp + Ghostty** — terminal surface quality bar.
7. **Zed / Delta** — editor and provenance-of-change ideas.
8. **Nimbalyst** — multi-editor + wiki-as-memory direction.
9. **LangSmith / Langfuse** — rendering long agent traces legibly.
10. **Emil Kowalski + Rauno Freiberg + shadcn/Base UI** — the craft layer under everything above.

**What not to copy:** Conductor's cloud-sandbox assumptions (Arkos is local-first), Vibe Kanban's
now-frozen visual language, Berd's acceptance that agents own the whole surface, and any peer's
tendency to make the human's own editing feel secondary. Arkos's differentiators are provider
breadth, worktree/handoff control, appearance control, and the workspace-tool dock — references
should sharpen those, not blur them into a generic agent chat.

---

## 8. Source list (with verification status)

Verified today by direct fetch **[V]**: conductor.build (+ /changelog), vibekanban.com,
github.com/BloopAI/vibe-kanban (README), github.com/block/berd (README via raw),
github.com/stravu/crystal → nimbalyst.com, omnara.com (README), claude.com/product/claude-code,
code.claude.com/docs/en/overview + /desktop, opencode.ai, zed.dev, delta.dev, linear.app,
raw.githubusercontent.com.

Seen in October 2026 news/queries, not opened **[N]**: GitHub Copilot app (github.blog),
BAND desktop (SiliconANGLE / DevOps.com / citybiz / TOKENPOST), Antigravity 2.0 (TechCrunch),
Claude Code desktop redesign + Routines and nested sessions (VentureBeat, Pasquale Pillitteri),
Codex desktop-control and Codex on Windows (remio, PCWorld), Cursor iOS app, Block Berd design
essay (block.xyz/inside).

From prior knowledge, canonical URL given **[K]**: Warp, Ghostty, Cursor, Codex app, Graphite,
Pierre, LangSmith, Langfuse, Sentry, Stripe, Notion, Things, Superhuman, Height, Family, Granola,
Amie, Resend, Clerk, Neon, PostHog, Supabase, tldraw, Excalidraw, Obsidian, Raycast, Arc/Dia,
Mobbin, Refero, SaaSFrame, Godly, Land-book, Design Details, plus the design-engineering people,
libraries and platform guidelines in section 4.2.

Unavailable from this machine (fetch failed): openai.com, cursor.com, warp.dev, raycast.com,
github.com HTML, block.xyz, graphite.dev, ghostty.org, ui.shadcn.com, vercel.com/geist.
