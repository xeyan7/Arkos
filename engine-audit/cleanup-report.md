# File cleanup scan — 19 October 2026

Scanned E:\app. No existing files were deleted or changed. This report and the JSON evidence files are new audit output.

## Main findings

121,166 regular files inventoried (3232.66 MiB of logical file sizes), excluding Git internals and files created by this scan. Symlink/junction targets were not recursively counted again. No traversal/read errors were reported.

13,292 files totaling **531.77 MiB** are strong cleanup candidates. These are old installations, an older packaged app, generated frontend files, and historical audit artifacts. Nothing here is an instruction to delete them automatically.

| Candidate | Files | Logical size | Evidence |
|---|---:|---:|---|
| [arkos-desktop/node_modules/.old_modules-ebf38ca398e739c7](E:/app/arkos-desktop/node_modules/.old_modules-ebf38ca398e739c7) | 13,201 | 159.23 MiB | Old dependency installation; no resolved dependency links target it. |
| [arkos-desktop/release](E:/app/arkos-desktop/release) | 82 | 369.34 MiB | Packaged v0.1.0 desktop; current source desktop package is v1.0.1. |
| [arkos-desktop/dist](E:/app/arkos-desktop/dist) | 3 | 0.41 MiB | Old root frontend build; current web build lives under apps/web/dist. |
| [engine-audit/dist](E:/app/engine-audit/dist) | 2 | 2.71 MiB | Old audit wheel; current engine explicitly blocks wheel/sdist distribution. |
| `engine-audit/*.log` | 4 | 0.09 MiB | Completed historical test/build logs; retain only for audit history. |

The old dependency folder accounts for 159.23 MiB. All 3,437 discovered links were considered for resolved targets; none that resolved pointed into `.old_modules-*`. This is strong evidence of an abandoned install, but is not proof against external tooling or unresolved links.

The release folder embeds `arkos-desktop` version `0.1.0`; the current desktop source package is `1.0.1`. SHA-256 comparison found 73 release files identical to the local Electron runtime, with zero differing matched files and 9 app-specific files absent from the runtime. The version, old bridge (`resources/bridge/host.py`), and old `main.cjs` entry point make this a strong obsolete-build candidate. Deleting it would remove that packaged version.

The root `arkos-desktop/dist/index.html` points at the old frontend assets. Current Vite config builds from `apps/web` into its own `dist`, and the current server uses `apps/server/dist/client`. The root folder may still matter to anyone using the old packaged workflow.

## Source files with no production consumers found

These are static-analysis findings, not runtime deletion validation. No source changes or tests were run.

| File | Finding |
|---|---|
| [arkos-desktop/apps/web/src/hooks/useComputerSupport.ts](E:/app/arkos-desktop/apps/web/src/hooks/useComputerSupport.ts) | No imports or other source references to the hook or its filename found. Strong unused-source candidate. |
| [arkos-desktop/apps/web/src/lib/pendingInteraction.ts](E:/app/arkos-desktop/apps/web/src/lib/pendingInteraction.ts) | No imports found. The live implementation of its stale-request predicate is in packages/shared/src/threadSummary.ts and is used by storeNormalization.ts. Strong leftover-helper candidate. |
| [arkos-desktop/apps/web/src/components/chat/project/projectAgentDialog.logic.ts](E:/app/arkos-desktop/apps/web/src/components/chat/project/projectAgentDialog.logic.ts) | Its three exports are referenced only by its own test. Candidate to remove together with the test, or connect to the actual feature if intended. |
| [arkos-desktop/apps/web/src/components/chat/project/projectAgentDialog.logic.test.ts](E:/app/arkos-desktop/apps/web/src/components/chat/project/projectAgentDialog.logic.test.ts) | Tests only the otherwise unused projectAgentDialog.logic.ts helper. Review as a pair. |
| [arkos-desktop/packages/shared/src/computerKeyNames.ts](E:/app/arkos-desktop/packages/shared/src/computerKeyNames.ts) | No consumer imports or symbol uses found. Still exposed by packages/shared/package.json, so removing it also requires removing the export and checking outside consumers. |

These five files total 8,521 bytes. Repository-wide symbol searches were used to review these candidates after the import scan. Dynamic or outside-repository consumers cannot be ruled out.

## Duplicate and empty files

SHA-256 checks found 29 groups of identical non-dependency, non-runtime, non-build files (0.50 MiB of theoretical duplicate payload). This does not establish that they are unnecessary. Brand assets have distinct development, beta, production, and platform paths referenced by the build. LaTeX template files are intentionally copied into self-contained templates. Icon names can be distinct API paths even when the SVG data matches. Keep them unless their consumers are changed.

The three empty Python `__init__.py` files are package markers. Empty does not mean unused.

## Keep by default

- Current node_modules and the .venv environment: installed dependencies. Removing them requires reinstalling and can break the developer launch.
- apps/desktop/dist-electron and apps/server/dist: current launch/build output, totaling 9.47 MiB.
- .arkos/electron-dev: local application state; treat it as user data.
- Browser test files, fixture entry points, Web Worker entry points, HTML entry points, and declaration files. Build/test configuration references them without normal imports.
- Lockfiles, patch files, licenses, third-party notices, optional skills, and platform resources.

## Limits and evidence

Sizes are logical file lengths, not promised reclaimed disk space. Bun may use hardlinks, and filesystem compression can change physical savings. Git internals were excluded. Source analysis inspected 5,184 tracked text files and checked static TypeScript/JavaScript import consumers, aliases, build entries, test discovery, and selected exported symbols. Python plugin/skill discovery was treated as dynamic; no Python source is asserted to be dead. Process command-line inspection was unavailable due to local CIM access restrictions; files in active use were not proven safe to delete.

Machine-readable results: [engine-audit/cleanup-inventory.json](E:/app/engine-audit/cleanup-inventory.json), [engine-audit/cleanup-verification.json](E:/app/engine-audit/cleanup-verification.json), [engine-audit/static-import-candidates.json](E:/app/engine-audit/static-import-candidates.json). The import candidate list is raw analysis and contains known entry-point/test-helper false positives explained above.
