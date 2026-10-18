# Arkos Beta

Arkos Beta is a packaged prerelease flavor of the desktop app. It is a separate application
that installs and updates side-by-side with stable Arkos, and it never shares stable's data
directory or update feed.

This document describes the flavor's behavior in a source checkout. No installers, update feed,
or hosted diagnostics service are published from this checkout; nothing here implies otherwise.

## The short version

- **Beta is named after the next Stable.** After `v0.9.2` ships, the next Beta version is
  `v0.9.3-beta.1`, then `v0.9.3-beta.2`, and so on until `v0.9.3` ships. Never version
  `v0.9.2-beta.1` after `v0.9.2`: it sorts older than the Stable it follows.
- **Two separate apps.** Arkos and Arkos Beta install side by side, with separate data
  (`~/.arkos` and `~/.arkos-beta`) and separate update feeds. A Beta update is never offered to
  Stable, and the other way round.
- **Data only copies Stable → Beta.** Settings > Try Beta copies the user's Stable data into
  Beta. Nothing is ever copied back: "Switch back to Arkos" reopens Stable with the data it
  already had.
- **Beta-only features** stay out of Stable through one list, `BETA_ONLY_FEATURES` in
  `packages/shared/src/betaFeatures.ts`. The code ships in both apps; Stable just switches
  listed features off. Remove the entry to promote a feature to Stable. See
  [Beta-only features](#beta-only-features).
- **Diagnostics are local by default.** Beta keeps diagnostic events locally. Uploads require an
  explicitly configured endpoint; Stable does not construct the diagnostics sender.

## Identity

- App name: `Arkos Beta`
- Bundle ID: `com.arkos.desktop.beta`
- Desktop origin: `arkos-beta://app`
- Arkos data: `~/.arkos-beta`
- Electron profile: `arkos-beta`
- Executable: `arkos-beta` (Linux AppImage bundle), `Arkos Beta.app`, `Arkos Beta.exe`
- Windows installer GUID: `a8e63b48-d4f3-4db5-9e12-368107afe65d` (separate Add/Remove
  Programs entry; the stable GUID is unchanged)

## App icon choices

**Settings → Appearance → App icon** offers Default, Icon, Dark, and Beta on
macOS. Windows and Linux offer Default, Icon, and Beta; Dark is macOS-only.
Default is the white Arkos artwork, Dark is black, Icon is the landscape artwork,
and Beta is the blue Beta artwork. A fresh Beta profile and Reset to defaults use
Beta; a saved choice is preserved.

On macOS 26, Beta uses the app's appearance-aware bundle icon. Earlier macOS
versions use its PNG artwork. Explicit Default and the other bitmap choices are
also written to the macOS app bundle so they survive quitting the app.
Stable keeps its existing picker choices. It does not offer Beta, and a stored
Beta preference remains inactive without being erased.

## How it differs from Canary

Canary is a local source-build flavor used for local-only testing; it never updates through the
packaged updater. Beta is a packaged flavor: it is built and signed the same way as stable, and
it updates through `electron-updater` like the production app.

## Update channel isolation

- Stable builds follow the `arkos` updater channel with `allowPrerelease=false` and only ever
  read the configured update repository's Latest release.
- Beta builds follow the `beta` updater channel with `allowPrerelease=true`.
  `electron-updater`'s GitHub provider reads the releases atom feed and takes the
  newest release that is not tagged for a custom channel — so if a stable
  release is newer than the latest beta tag, beta installs see "no update"
  until the next beta release is cut. Always cut a new beta right after each
  stable release.
- Beta releases carry `beta-mac.yml`, `beta.yml`, and `beta-linux.yml`
  manifests. The `latest-*.yml` files may be present on beta releases too, but
  they are inert there: stable installs only read them from the Latest
  release, which beta tags never become. A beta release can never be offered
  to a stable install, and a stable release never carries beta manifests.
- The desktop additionally gate-checks every candidate's version against its
  lane (`isUpdateVersionAllowedForFlavor`): beta installs accept only
  `*-beta.*` versions and production installs accept only stable versions.
  This matters because `electron-updater`'s GitHub provider falls back to
  `latest-mac.yml` when the channel manifest is absent — without the gate, a
  beta install could be offered a stable build, and installing it would
  silently swap the app to the other flavor and home directory. Crossing lanes
  always happens by installing the other app, never by update.
- `allowDowngrade` stays `false` on both trains; moving back to stable happens
  by opening the stable app (see [Leaving beta](#leaving-beta)), never by update.
- Pending-update caches are scoped per flavor (`~/Library/Caches/arkos-desktop-beta-updater`
  on macOS), so a downloaded beta update never collides with stable's pending
  update state.

## Signing

Beta builds use the same signing and notarization setup as stable. A Windows build must be
signed before it is distributed; an unsigned build is a local artifact only, never something to
hand to another machine.

## Flavor selection

The packaged flavor is `production` (default), `canary`, `cua`, or `beta`. The
`ARKOS_DESKTOP_FLAVOR` environment variable selects it for a local build, and the packaged
`package.json` embeds the resolved flavor (`arkosDesktopFlavor`), so a packaged build cannot
silently lose its identity at runtime: on packaged builds the embedded value wins over the
environment variable.

## Joining beta from stable

The stable app offers a one-click handoff under **Settings → General → Arkos Beta**:

- **Install Arkos Beta** (macOS) downloads the newest `v*-beta.N` release's
  `beta-mac.yml`, picks the zip for the current architecture, verifies its
  sha512, unpacks it with `ditto`, checks the bundle id is
  `com.arkos.desktop.beta`, and verifies the code signature is valid
  and signed by the same team id as the running app (`codesign --verify
--deep --strict` plus a `TeamIdentifier` match; skipped when the running
  build is itself unsigned). Only then is `Arkos Beta.app` moved into
  `/Applications` — then opened. On other platforms the card opens the
  configured release page when one is set.
- **Copy my data and open** installs first when needed, then writes a marker at
  `~/.arkos-beta/import-requested.json` and launches the beta app. On its next
  startup the beta server consumes the marker, snapshots stable's database,
  copies settings and provider secrets, then deletes the marker. The button
  first confirms that this replaces existing Beta chats, projects, and settings;
  work created only in Beta will be lost, while Stable remains unchanged. The snapshot
  uses `VACUUM INTO` when the source is quiescent; while stable is running it
  holds `state.sqlite` under `PRAGMA locking_mode = EXCLUSIVE`, so the importer
  falls back to a file-level copy of the database and its WAL, retried until no
  checkpoint or WAL restart landed mid-copy (it fails rather than import a torn
  pair), and vacuums that staged copy into a checkpointed snapshot. Either way
  the result is a consistent point-in-time copy and the outcome is written to
  `~/.arkos-beta/import-result.json` so the stable settings card can report
  success or the failure reason. The importer stages every file first, rejects
  symbolic links in copied state, and rolls back normal filesystem commit errors
  rather than reporting success with only part of the state copied.
- Only a packaged beta (`ARKOS_DESKTOP_BUNDLE_ID` is the beta bundle id)
  consumes the marker, and only from stable's data folder (`ARKOS_STABLE_HOME`
  handed over by stable, else `~/.arkos`). A stray marker in any other home
  is ignored.
- If stable's database has migrations newer than the installed beta knows, the
  import fails with "Update Arkos Beta" instead of leaving beta unable to
  start. Any leftover beta `state.sqlite-wal`/`-shm`/`-journal` is removed
  before the snapshot is swapped in, so an old WAL cannot replay over it.
- **Open Beta** launches the installed beta app without touching data.
- The import button is disabled while a beta server is running so an in-flight
  beta never reads a half-written snapshot; quit beta first, then import.
- Launch/import are refused unless the running app is a production-flavor build.
- On macOS the beta app is spawned by executable path
  (`Arkos Beta.app/Contents/MacOS/Arkos Beta`) with a sanitized environment:
  stable's `ARKOS_HOME`, `ARKOS_DESKTOP_SMOKE_USER_DATA`, and server auth
  variables are stripped, and beta gets `ARKOS_BETA_HOME` (plus
  `ARKOS_DESKTOP_SMOKE_USER_DATA` when `ARKOS_BETA_USER_DATA` is set).

The marker format lives in `packages/shared/src/betaChannel.ts`
(`BetaImportRequest`, `BetaImportResult`); the desktop side is
`apps/desktop/src/betaChannel.ts`, the download/install flow is
`apps/desktop/src/betaInstaller.ts`, and the consuming import is
`apps/server/src/betaImport.ts`.

### Local demo

Everything about the install location and data home can be redirected with
environment variables, so a demo never touches a real `~/.arkos`,
`~/Library/Application Support/arkos`, or `/Applications`:

- `ARKOS_BETA_FEED_URL` — base URL serving `beta-mac.yml` and the files it
  lists (for example a local static server). Without it, the newest GitHub
  `v*-beta.N` release is used.
- `ARKOS_BETA_INSTALL_DIR` — directory the app bundle is moved into and
  probed in first (default `/Applications`).
- `ARKOS_BETA_HOME` — overrides `~/.arkos-beta` everywhere it is resolved:
  stable's import marker path, the beta app's own base dir, and the
  running-server probe.
- `ARKOS_BETA_USER_DATA` — Electron `userData` dir handed to the launched
  beta (only honored on the beta and cua flavors and source builds).
- `ARKOS_HOME` / `HOME` — stable's data dir (beta ignores `ARKOS_HOME`, so a
  globally exported value can never point beta at stable's data) and the
  `userData` base, respectively; overriding `HOME` isolates the Electron profile
  from a real user profile.

The import copies settings, provider secrets, and a database snapshot. It never
copies logs, diagnostics queues, runtime files, other import markers, database
sidecars (`state.sqlite-wal`/`-shm`/`-journal`), or `*.lifecycle-lock`
directories — a leaked lock directory would make beta refuse to start while the
stable process is alive. Nothing is ever written into the stable home: the
marker and the result both live in the beta home.

## Leaving beta

Beta shows **Switch back to Arkos** under **Settings → General**. It opens
stable and quits beta; on macOS it can also move `Arkos Beta.app` to the Trash
(checked by default). Stable was never changed by the switch, so it opens with
the chats and settings it had before.

- Beta data is never copied back. Beta can carry database migrations and data
  for features stable does not have yet, so a copy could fail or corrupt
  stable's `state.sqlite`. The dialog says so plainly. `~/.arkos-beta` is
  kept, so reinstalling beta picks up where the user left off.
- Stable is found through `ARKOS_STABLE_EXECUTABLE`, which stable sets on the
  beta it launches (with `ARKOS_STABLE_HOME` for its data dir), then through
  `/Applications/Arkos.app`, `~/Applications/Arkos.app`, or the stable NSIS
  uninstall key on Windows. When none is found the card offers the
  configured stable release page when one is set.
- Stable is spawned with beta's per-process overrides stripped
  (`ARKOS_DESKTOP_SMOKE_USER_DATA`, server auth variables) and `ARKOS_HOME`
  restored from `ARKOS_STABLE_HOME` when stable handed one over. An already
  running stable just comes to the front through its single-instance lock.
- The Trash step only runs for a packaged bundle named `Arkos Beta.app`, so a
  source or dev build can never trash Electron itself.

## Beta-only features

`packages/shared/src/betaFeatures.ts` holds `BETA_ONLY_FEATURES`, the single
list of features that ship in Beta but not in Stable. `isBetaFeatureEnabled`
turns a listed feature off only for the `production` desktop flavor; Beta,
Cua, Canary, development, and non-desktop hosts keep it.

To put a feature behind the list:

- Add its key to `BETA_ONLY_FEATURES`.
- Gate it on the server, which is authoritative: resolve the host flavor with
  `desktopFlavorFromBundleId(process.env[ARKOS_DESKTOP_BUNDLE_ID_ENV])` and
  refuse the capability there, not just in the UI.
- Hide it on the web with a constant built from
  `desktopFlavorFromProtocol(window.location.protocol, import.meta.env.DEV)` —
  hide entry points rather than disabling them, and coerce any persisted or
  replayed value to off so stale state cannot re-arm the feature.
- Keep any migrations or persisted fields additive and inert on Stable; a
  user's stored preference must survive a Beta → Stable round trip untouched.

Promote a feature to Stable by deleting its entry; every gate resolves itself.

The list currently contains `groups` (Hubs), gated off in Stable.
Tasks, Inbox, and Auto-fix CI are available in both apps.
Oh My Pi, the rail sidebar layout, and message trail
sound are available in both Stable and Beta.

On Stable, Hubs are inert rather than hidden data: the server refuses the hub
APIs, Library routes and gateway tools, stops coordinator wakes and monitoring,
leaves saved Hub check-ins and completion evaluations unchanged and unscheduled,
uses ordinary Arkos tool approvals for former coordinator chats, and refuses
creating a hub; the web hides the Hubs tab, route, setting, and
thread actions, and shows any existing hub folder as an ordinary project so its
chats stay reachable. The gate lives in
`apps/server/src/projectAgent/groupsBetaGate.ts` and `GROUPS_ON` in
`apps/web/src/betaFeatures.ts`.

Tasks and its delegation APIs are available in Stable and Beta. Tasks takes
Kanban's navigation slot and preserves its saved order and visibility; its
List / Kanban switch keeps the board accessible. A client connected to an older
server that refuses Tasks returns to Kanban.

Inbox and its `stats.getRecap` RPC are available in Stable and Beta. Stable shows
chat attention, running and finished work, review requests, and the activity recap.
The to-do list, quick-add, delegation card, and **All tasks** link appear only where
Tasks is available, including Stable and Beta.

`pull-request-auto-fix` enables the opt-in **Auto-fix CI** action in a pull
request's menu. The server watches checks for an enabled PR and can ask its
linked agent chat to address failures in both Stable and Beta. It keeps the chat
permissions and retry limits, and waits for active work, approvals, and questions.
This does not enable automatic merging.

Message trail sound is opt-in under **Settings → Chat → Message trail sound**
on macOS desktop in both Stable and Beta. It follows system audio (macOS 14.2+),
the microphone, or both. The desktop IPC handler refuses other platforms,
and the web hides the selector on hosts without a supported desktop bridge.
Only loudness levels are sent to the trail, and the reader stops when the
visible trail no longer subscribes. First use can request macOS audio access.

## Diagnostics

Beta diagnostics remain local by default. Set `ARKOS_BETA_DIAGNOSTICS_URL` only to an ingestion
service you control to enable event and crash uploads. No hosted Arkos diagnostics service is
configured in this checkout.

## Data

Without an explicit import, beta starts with an empty `~/.arkos-beta` home. It
does not copy, share, or migrate stable (`~/.arkos`) or Canary
(`~/.arkos-canary`) data on its own. Both apps can run at the same time: the
server binds an ephemeral port, single-instance locks are scoped per Electron
`userData`, and provider secrets are file-scoped inside each home.
