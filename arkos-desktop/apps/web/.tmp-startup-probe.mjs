// Detailed startup probe: breaks the renderer module waterfall down by source.
// Run from apps/web: node .tmp-startup-probe.mjs --runs 2 --home warm
import { _electron as electron } from "playwright";
import { createRequire } from "node:module";
import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};
const runs = Number(opt("runs", "2"));
const homeMode = opt("home", "warm");
const url = opt("url", "http://localhost:5733");

const webDir = process.cwd();
const desktopDir = resolve(webDir, "../desktop");
const electronPath = createRequire(join(desktopDir, "package.json"))("electron");
const sourceHome = resolve(desktopDir, "../../.arkos/electron-dev");
const outRoot = resolve(desktopDir, "../../.arkos/startup-perf");
mkdirSync(outRoot, { recursive: true });
const runDir = mkdtempSync(join(outRoot, "probe-"));
const samples = [];

function killTree(child) {
  if (process.platform === "win32" && child.pid && child.exitCode === null) {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else if (child.exitCode === null) {
    child.kill("SIGTERM");
  }
}

for (let index = 0; index < runs; index++) {
  const home = join(runDir, `home-${index}`);
  if (homeMode === "warm" && existsSync(sourceHome)) {
    cpSync(sourceHome, home, {
      recursive: true,
      filter: (src) => !/lifecycle-lock|\.log$/.test(src),
    });
  } else {
    mkdirSync(home, { recursive: true });
  }

  const env = {
    ...process.env,
    ARKOS_HOME: home,
    ARKOS_DESKTOP_SMOKE_USER_DATA: join(runDir, `chromium-${index}`),
    ARKOS_SOURCE_DESKTOP_BUILD_MARKER: "arkos-source-desktop-build-v2",
    VITE_DEV_SERVER_URL: url,
    ELECTRON_RENDERER_PORT: new URL(url).port || "80",
  };
  delete env.ELECTRON_RUN_AS_NODE;

  const startedAt = performance.now();
  const app = await electron.launch({
    executablePath: electronPath,
    args: ["dist-electron/main.js"],
    cwd: desktopDir,
    env,
    timeout: 90_000,
  });
  const stages = {};
  app.process().stdout?.on("data", (data) => {
    for (const match of String(data).matchAll(/\[desktop-startup\] ([\w-]+) (\d+)ms/g)) {
      stages[match[1]] = Number(match[2]);
    }
  });

  try {
    let page;
    while (
      !(page = app.windows().find((candidate) => candidate.url().startsWith(url)))
    ) {
      if (performance.now() - startedAt > 90_000) throw new Error("App renderer did not open");
      await new Promise((r) => setTimeout(r, 20));
    }
    const firstWindowMs = performance.now() - startedAt;
    await page.evaluate(() => performance.setResourceTimingBufferSize(20_000));
    while (
      !(await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows().some((w) => w.isVisible()),
      ))
    ) {
      if (performance.now() - startedAt > 90_000) throw new Error("Window never visible");
      await new Promise((r) => setTimeout(r, 20));
    }
    const windowVisibleMs = performance.now() - startedAt;
    await page.waitForFunction(
      () => document.querySelector('[data-slot="sidebar-trigger"]') !== null,
      undefined,
      { timeout: 90_000, polling: 50 },
    );
    const shellReadyMs = performance.now() - startedAt;

    const detail = await page.evaluate(() => {
      const resources = performance.getEntriesByType("resource");
      const groups = {};
      const add = (key, entry) => {
        const g = (groups[key] ??= { count: 0, bytes: 0, ms: 0 });
        g.count += 1;
        g.bytes += entry.decodedBodySize || 0;
        g.ms += entry.duration || 0;
      };
      for (const entry of resources) {
        let pathname;
        try {
          pathname = new URL(entry.name).pathname;
        } catch {
          continue;
        }
        if (pathname.startsWith("/node_modules/.vite/deps/")) add("prebundled-dep", entry);
        else if (pathname.startsWith("/node_modules/")) add("raw-node-module", entry);
        else if (pathname.startsWith("/src/")) add("app-source", entry);
        else if (pathname.startsWith("/@")) add("vite-internal", entry);
        else add("other", entry);
      }
      const scripts = resources.filter((entry) => entry.initiatorType === "script");
      const byDuration = [...scripts]
        .sort((a, b) => b.duration - a.duration)
        .slice(0, 20)
        .map((entry) => ({
          path: new URL(entry.name).pathname,
          startMs: Math.round(entry.startTime),
          durationMs: Math.round(entry.duration),
          bytes: entry.decodedBodySize,
        }));
      const byBytes = [...scripts]
        .sort((a, b) => (b.decodedBodySize || 0) - (a.decodedBodySize || 0))
        .slice(0, 20)
        .map((entry) => ({
          path: new URL(entry.name).pathname,
          bytes: entry.decodedBodySize,
        }));
      const navigation = performance.getEntriesByType("navigation")[0];
      return {
        groups,
        totalScripts: scripts.length,
        byDuration,
        byBytes,
        domContentLoadedMs: navigation?.domContentLoadedEventEnd ?? null,
        fcpMs: performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? null,
        marks: performance
          .getEntriesByType("mark")
          .filter((entry) => entry.name.startsWith("arkos-startup:"))
          .map((entry) => ({ name: entry.name.replace("arkos-startup:", ""), ms: Math.round(entry.startTime) })),
      };
    });

    samples.push({ firstWindowMs, windowVisibleMs, shellReadyMs, stages, ...detail });
    console.log(
      JSON.stringify({
        sample: index + 1,
        homeMode,
        windowVisibleMs: Math.round(windowVisibleMs),
        shellReadyMs: Math.round(shellReadyMs),
        totalScripts: detail.totalScripts,
        groups: detail.groups,
        marks: detail.marks,
        stages,
      }),
    );
  } finally {
    const child = app.process();
    try {
      await Promise.race([app.close(), new Promise((r) => setTimeout(r, 4_000))]);
    } catch {
      /* fall through to kill */
    }
    killTree(child);
  }
}

const median = (key) =>
  samples.map((s) => s[key]).sort((a, b) => a - b)[Math.floor(samples.length / 2)];
const report = {
  homeMode,
  url,
  runs,
  medianWindowVisibleMs: median("windowVisibleMs"),
  medianShellReadyMs: median("shellReadyMs"),
  samples,
};
const reportPath = join(runDir, "probe-report.json");
writeFileSync(reportPath, JSON.stringify(report, null, 2));
console.log(
  JSON.stringify({
    reportPath,
    medianWindowVisibleMs: Math.round(report.medianWindowVisibleMs),
    medianShellReadyMs: Math.round(report.medianShellReadyMs),
  }),
);
