# Arkos launch instructions

When a user asks to launch Arkos Electron, do not install the desktop application. Launch it directly from the source checkout in developer mode.

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
