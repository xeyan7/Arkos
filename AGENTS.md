# Arkos launch instructions

When a user asks to launch Arkos Electron, do not install the desktop application. Launch it directly from the source checkout in developer mode.

## Never install unless explicitly asked

Starting the desktop app never means installing it. Whenever the user asks to start the desktop app in developer mode — or asks to start the desktop app in any other way, or anything related to starting it — never install the desktop app until the user clearly and explicitly instructs you to install it. Just start it in developer mode. Do not install it on the desktop. Only start it in developer mode.

## Standard developer launch

From `E:\app\arkos-desktop`, restore project dependencies if needed, build the desktop and backend, then start Electron:

```powershell
bun install --frozen-lockfile
$env:NODE_OPTIONS = '--max-old-space-size=8192'
bun run build:desktop --env-mode=loose
bun run electron:dev -- -- --env-mode=loose
```

The Electron runtime downloaded as a project dependency is sufficient; no packaged Arkos installer is required. `electron:dev` uses the separate `.arkos/electron-dev` data folder.

## Reuse an already running web frontend

If the web frontend is already running at `http://localhost:5733` and the desktop and backend have been built, launch Electron directly:

```powershell
cd E:\app\arkos-desktop\apps\desktop
$env:ARKOS_HOME = 'E:\app\arkos-desktop\.arkos\electron-dev'
$env:VITE_DEV_SERVER_URL = 'http://localhost:5733'
$env:ELECTRON_RENDERER_PORT = '5733'
bun run dev:electron
```

Use the frontend's actual port if it differs. Check existing development processes before starting duplicates. Verify that the Electron window and its backend start successfully before reporting completion.

## Reporting back to the user

Accuracy first: never claim something works, is fixed, or is verified when you have not actually
checked it. Say what you verified and what you did not.

Then make the summary easy to read:

- Lead with what changed and what it means for the user. Put the specifics after — file paths,
  counts, commands, exact names.
- Use simple, direct words. Short sentences. Everyday vocabulary instead of internal jargon,
  or shorthand the user never used themselves.
- When you must use a technical term, explain it in the same sentence, or describe the effect
  instead of the mechanism.
- State clearly what is finished, what is still open, and what needs a decision from the user.
- Keep it short. If the summary takes longer to read than the change took to make, cut it down.
