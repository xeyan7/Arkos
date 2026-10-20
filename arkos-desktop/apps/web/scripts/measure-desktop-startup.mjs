// Measure source Electron launches without touching the user's active profile.
// Run from apps/web: node scripts/measure-desktop-startup.mjs --label before --runs 3
import { _electron as electron } from "playwright";
import { createRequire } from "node:module";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const desktopDir = fileURLToPath(new URL("../../desktop/", import.meta.url));
const repoRoot = resolve(desktopDir, "../..");
const executablePath = createRequire(join(desktopDir, "package.json"))("electron");
const options = {
  label: "startup",
  runs: 3,
  url: "http://localhost:5733",
  profile: false,
  bundled: false,
  evidence: false,
};
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i].replace(/^--/, "");
  if (!(key in options) || !process.argv[i + 1]) throw new Error("Use --label, --runs, or --url");
  options[key] =
    key === "runs"
      ? Number(process.argv[i + 1])
      : key === "profile" || key === "bundled" || key === "evidence"
        ? /^(1|true)$/.test(process.argv[i + 1])
        : process.argv[i + 1];
}
if (!Number.isInteger(options.runs) || options.runs < 1 || options.runs > 10) {
  throw new Error("--runs must be an integer from 1 to 10");
}
const outputDir = join(repoRoot, ".arkos", "startup-perf");
mkdirSync(outputDir, { recursive: true });
// Fail immediately for a wrong port instead of spending a minute watching an
// Electron network-error page and then masking that error during shutdown.
if (!options.bundled) {
  const response = await fetch(options.url, { signal: AbortSignal.timeout(5_000) });
  if (!response.ok) throw new Error(`Frontend unavailable: ${response.status} ${options.url}`);
}
const runDir = mkdtempSync(join(outputDir, "sample-"));
const samples = [];

for (let index = 0; index < options.runs; index++) {
  const env = {
    ...process.env,
    ARKOS_HOME: join(runDir, `home-${index}`),
    ARKOS_DESKTOP_SMOKE_USER_DATA: join(runDir, `chromium-${index}`),
    ARKOS_SOURCE_DESKTOP_BUILD_MARKER: "arkos-source-desktop-build-v2",
    VITE_DEV_SERVER_URL: options.url,
    ELECTRON_RENDERER_PORT: new URL(options.url).port || "80",
    ARKOS_BUNDLED_RENDERER: options.bundled ? "1" : "0",
  };
  delete env.ELECTRON_RUN_AS_NODE;
  const startedAt = performance.now();
  const app = await electron.launch({
    executablePath,
    args: ["dist-electron/main.js"],
    cwd: desktopDir,
    env,
    timeout: 60_000,
  });
  console.log(
    JSON.stringify({
      sample: index + 1,
      phase: "electron-connected",
      elapsedMs: performance.now() - startedAt,
    }),
  );
  const stages = {};
  const errors = [];
  const child = app.process();
  app.process().stdout?.on("data", (data) => {
    for (const match of String(data).matchAll(/\[desktop-startup\] ([\w-]+) (\d+)ms/g))
      stages[match[1]] = Number(match[2]);
  });
  try {
    // Detached DevTools can be the first Playwright window; measure the app itself.
    let page;
    while (
      !(page = app
        .windows()
        .find((candidate) =>
          candidate.url().startsWith(options.bundled ? "arkos://app" : options.url),
        ))
    ) {
      if (performance.now() - startedAt > 60_000) throw new Error("App renderer did not open");
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    console.log(
      JSON.stringify({
        sample: index + 1,
        phase: "first-window",
        elapsedMs: performance.now() - startedAt,
        url: page.url(),
      }),
    );
    page.on("pageerror", (error) => errors.push(error.message));
    if (options.evidence) {
      await page.evaluate(() => {
        window.__startupFrames = [];
        let previous;
        const sample = () => {
          const root = document.getElementById("root");
          const state = root?.querySelector('[data-slot="sidebar-trigger"]')
            ? "shell"
            : root?.querySelector('.app-boot-splash, img, svg, [role="status"]')
              ? "loading"
              : root?.textContent?.trim()
                ? "text"
                : "blank";
          if (state !== previous) window.__startupFrames.push({ state, ms: performance.now() });
          previous = state;
          if (state !== "shell") requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
      });
    }
    await page.evaluate(() => performance.setResourceTimingBufferSize(10_000));
    const profiler = options.profile ? await page.context().newCDPSession(page) : null;
    if (profiler) {
      await profiler.send("Profiler.enable");
      await profiler.send("Profiler.start");
    }
    while (
      !(await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows().some((window) => window.isVisible()),
      ))
    ) {
      if (performance.now() - startedAt > 60_000) throw new Error("Window did not become visible");
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    const windowVisibleMs = performance.now() - startedAt;
    await page.waitForFunction(
      () => document.querySelector('[data-slot="sidebar-trigger"]') !== null,
      undefined,
      { timeout: 60_000, polling: 50 },
    );
    const shellReadyMs = performance.now() - startedAt;
    let usableMs;
    let startupFrames;
    if (options.evidence) {
      await page
        .locator('[contenteditable="true"][role="textbox"]')
        .first()
        .waitFor({ timeout: 60_000 });
      usableMs = performance.now() - startedAt;
      startupFrames = await page.evaluate(() => window.__startupFrames);
      await page.screenshot({ path: join(runDir, `usable-${index}.png`) });
    }
    let hotFunctions;
    if (profiler) {
      const { profile } = await profiler.send("Profiler.stop");
      writeFileSync(join(runDir, `cpu-${index}.json`), JSON.stringify(profile));
      const cost = new Map();
      for (let i = 0; i < (profile.samples?.length ?? 0); i++)
        cost.set(
          profile.samples[i],
          (cost.get(profile.samples[i]) ?? 0) + (profile.timeDeltas?.[i] ?? 0) / 1000,
        );
      hotFunctions = profile.nodes
        .map((node) => ({
          name: node.callFrame.functionName,
          url: node.callFrame.url.split("?")[0],
          ms: cost.get(node.id) ?? 0,
        }))
        .sort((a, b) => b.ms - a.ms)
        .slice(0, 20);
    }
    const metrics = await page.evaluate(async () => {
      const longTasks = [];
      const observer = new PerformanceObserver((list) =>
        longTasks.push(...list.getEntries().map((entry) => entry.duration)),
      );
      observer.observe({ type: "longtask", buffered: true });
      await new Promise((resolve) => setTimeout(resolve, 100));
      observer.disconnect();
      const navigation = performance.getEntriesByType("navigation")[0];
      const resources = performance.getEntriesByType("resource");
      return {
        firstContentfulPaintMs:
          performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? null,
        domContentLoadedMs: navigation?.domContentLoadedEventEnd ?? null,
        scriptRequests: resources.filter((entry) => entry.initiatorType === "script").length,
        rendererStages: performance
          .getEntriesByType("mark")
          .filter((entry) => entry.name.startsWith("arkos-startup:"))
          .map((entry) => ({ name: entry.name, ms: entry.startTime })),
        scriptDecodedBytes: resources
          .filter((entry) => entry.initiatorType === "script")
          .reduce((sum, entry) => sum + entry.decodedBodySize, 0),
        iconScripts: resources
          .filter((entry) => /react-icons|@tabler/.test(entry.name))
          .map((entry) => ({
            path: new URL(entry.name).pathname,
            bytes: entry.decodedBodySize,
            ms: entry.duration,
          })),
        lateScripts: resources
          .filter((entry) => entry.initiatorType === "script")
          .sort((a, b) => b.responseEnd - a.responseEnd)
          .slice(0, 8)
          .map((entry) => ({
            path: new URL(entry.name).pathname,
            startMs: entry.startTime,
            endMs: entry.responseEnd,
          })),
        longTaskCount: longTasks.length,
        longTaskTotalMs: longTasks.reduce((sum, duration) => sum + duration, 0),
      };
    });
    const devToolsOpen = await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows().some((window) => window.webContents.isDevToolsOpened()),
    );
    const sample = {
      windowVisibleMs,
      shellReadyMs,
      usableMs,
      startupFrames,
      ...metrics,
      devToolsOpen,
      stages,
      errors,
      hotFunctions,
    };
    samples.push(sample);
    console.log(JSON.stringify({ sample: index + 1, ...sample }));
  } finally {
    // Only terminate this isolated measurement process tree, never the running app.
    let closeTimer;
    try {
      await Promise.race([
        app.close(),
        new Promise((_, reject) => {
          closeTimer = setTimeout(() => reject(new Error("Benchmark shutdown timed out")), 5_000);
        }),
      ]);
    } catch {
      if (process.platform === "win32" && child.pid && child.exitCode === null) {
        spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
      } else if (child.exitCode === null) child.kill("SIGTERM");
    } finally {
      clearTimeout(closeTimer);
    }
  }
}
const median = (key) =>
  samples.map((sample) => sample[key]).sort((a, b) => a - b)[Math.floor(samples.length / 2)];
const report = {
  label: options.label,
  renderer: options.bundled ? "bundled local protocol" : "live server",
  url: options.url,
  profile: "fresh isolated profile per sample; existing Vite server",
  samples,
  medianWindowVisibleMs: median("windowVisibleMs"),
  medianShellReadyMs: median("shellReadyMs"),
};
const reportPath = join(runDir, "report.json");
writeFileSync(reportPath, JSON.stringify(report, null, 2));
console.log(
  JSON.stringify({
    reportPath,
    medianWindowVisibleMs: report.medianWindowVisibleMs,
    medianShellReadyMs: report.medianShellReadyMs,
  }),
);
