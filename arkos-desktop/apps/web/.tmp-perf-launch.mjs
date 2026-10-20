import { _electron as electron } from "playwright";
import { resolve } from "node:path";
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";

const desktopDir = resolve(process.cwd(), "../desktop");
const electronPath = resolve(
  desktopDir,
  "../../node_modules/.bun/electron@43.4.1/node_modules/electron/dist/electron.exe",
);
const sourceHome = resolve(desktopDir, "../../.arkos/electron-dev");
const profileHome = resolve(desktopDir, "../../.arkos/perf-profile");
const profileUserData = resolve(process.cwd(), ".tmp-perf-userdata");

if (existsSync(profileHome)) rmSync(profileHome, { recursive: true, force: true });
mkdirSync(profileHome, { recursive: true });
if (existsSync(sourceHome)) {
  cpSync(sourceHome, profileHome, {
    recursive: true,
    filter: (src) => !src.includes("state.sqlite.lifecycle-lock"),
  });
}
rmSync(profileUserData, { recursive: true, force: true });

const childEnv = {
  ...process.env,
  ARKOS_HOME: profileHome,
  ARKOS_DESKTOP_SMOKE_USER_DATA: profileUserData,
  ARKOS_SOURCE_DESKTOP_BUILD_MARKER: "arkos-source-desktop-build-v2",
  VITE_DEV_SERVER_URL: "http://localhost:4173",
  ELECTRON_RENDERER_PORT: "4173",
};
delete childEnv.ELECTRON_RUN_AS_NODE;

const startedAt = performance.now();
const app = await electron.launch({
  executablePath: electronPath,
  args: ["dist-electron/main.js"],
  cwd: desktopDir,
  env: childEnv,
  timeout: 120_000,
});

function sinceStart() {
  return ((performance.now() - startedAt) / 1000).toFixed(2) + "s";
}

async function waitForAppPage(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const page of app.windows()) {
      if (page.url().startsWith("http://localhost:4173")) return page;
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  return null;
}

app.on("window", (page) => console.log("window event", sinceStart(), page.url()));
app.process().stderr?.on("data", (data) => {
  const text = String(data).trim();
  if (text.length > 0) console.log("[stderr]", text.slice(0, 500));
});
app.process().stdout?.on("data", (data) => {
  const text = String(data).trim();
  if (text.length > 0) console.log("[stdout]", text.slice(0, 500));
});

try {
  const page = await waitForAppPage(90_000);
  if (!page) {
    console.log("no app page; windows:", app.windows().map((w) => w.url()));
    console.log("windows after wait", sinceStart());
  } else {
    console.log("app page", sinceStart(), page.url());
    page.on("console", (message) => {
      const text = message.text();
      if (text.trim().length > 0) console.log("[renderer]", message.type(), text.slice(0, 300));
    });
    page.on("pageerror", (error) => console.log("[pageerror]", error.message));
    await page.waitForLoadState("domcontentloaded", { timeout: 90_000 }).catch(() => {});
    console.log("domcontentloaded", sinceStart());
    await page.waitForTimeout(8_000);
    console.log("title", await page.title());
    console.log("url", page.url());
    const snapshot = await page.evaluate(() => ({
      text: document.body.innerText.slice(0, 2000),
      timing: performance.getEntriesByType("navigation")[0]
        ? {
            domContentLoaded: performance.getEntriesByType("navigation")[0].domContentLoadedEventEnd,
            load: performance.getEntriesByType("navigation")[0].loadEventEnd,
            responseEnd: performance.getEntriesByType("navigation")[0].responseEnd,
          }
        : null,
    }));
    console.log(JSON.stringify(snapshot, null, 2));
    await page.screenshot({ path: resolve(process.cwd(), ".tmp-perf-launch.png") }).catch((error) => {
      console.log("screenshot failed", error.message);
    });
  }
} catch (error) {
  console.error("FAILED", error);
} finally {
  const childProcess = app.process();
  if (childProcess.pid) {
    spawnSync("taskkill", ["/pid", String(childProcess.pid), "/t", "/f"], { stdio: "ignore" });
  }
}
