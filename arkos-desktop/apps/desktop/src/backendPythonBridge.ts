import { createServer, type ServerResponse } from "node:http";
import { createInterface } from "node:readline";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { randomUUID } from "node:crypto";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { spawnProcess } from "@arkos/shared/processRuntime";

interface EngineConfig {
  engine: string;
  python?: string;
  configHome?: string;
}

interface EngineSession {
  child: ChildProcessWithoutNullStreams;
  ready: Promise<void>;
  response?: ServerResponse;
  running: boolean;
}

/** Electron owns the Python children; the backend only receives a loopback capability. */
export async function startPythonBridge(options: {
  appPath: string;
  userData: string;
  log: (message: string) => void;
}) {
  let root = resolve(options.appPath);
  while (!existsSync(join(root, "bridge", "arkos_bridge.py"))) {
    const parent = dirname(root);
    if (parent === root) throw new Error("Cannot locate bridge/arkos_bridge.py");
    root = parent;
  }
  const config: EngineConfig = JSON.parse(readFileSync(join(root, "bridge", "config.json"), "utf8"));
  const engine = resolve(root, config.engine);
  const candidates = [
    config.python && resolve(root, config.python),
    join(engine, ".venv", "Scripts", "python.exe"),
    join(engine, "venv", "Scripts", "python.exe"),
    join(homedir(), "AppData", "Local", "arkos", "arkos-agent", "venv", "Scripts", "python.exe"),
  ];
  const python = candidates.find((candidate): candidate is string => Boolean(candidate && existsSync(candidate)))
    ?? "python";
  if (!python) throw new Error("No Arkos Python runtime found; set python in bridge/config.json");
  const token = randomUUID();
  const sessions = new Map<string, EngineSession>();
  let closing = false;

  function start(id: string, cwd?: string): EngineSession {
    const previous = sessions.get(id);
    if (previous) return previous;
    if (closing) throw new Error("Python bridge is shutting down");
    const args = ["-B", "-u", join(root, "bridge", "arkos_bridge.py"),
      "--engine", engine, "--home", join(options.userData, "engine"), "--session", id];
    if (config.configHome) args.push("--config-home", config.configHome);
    const child = spawnProcess(python!, args, {
      cwd: cwd || engine, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" }, stdio: "pipe",
    });
    let onReady: () => void;
    let onFailure: (error: Error) => void;
    const ready = new Promise<void>((yes, no) => { onReady = yes; onFailure = no; });
    // Attach immediately: readiness can fail before the HTTP request awaits it.
    void ready.catch(() => {});
    const session: EngineSession = { child, ready, running: false };
    sessions.set(id, session);
    const timeout = setTimeout(() => {
      onFailure(new Error("Arkos Python import timed out after 90 seconds"));
      child.kill();
    }, 90_000);
    createInterface({ input: child.stdout }).on("line", (line) => {
      try {
        const event = JSON.parse(line);
        if (event.event === "ready") {
          clearTimeout(timeout);
          onReady();
          options.log(`Python ready session=${id}`);
        }
        if (event.event === "fatal") {
          clearTimeout(timeout);
          onFailure(new Error(String(event.message)));
        }
        session.response?.write(JSON.stringify(event) + "\n");
        if (event.event === "completed" || event.event === "fatal") {
          session.running = false;
          session.response?.end();
          delete session.response;
        }
      } catch (error) {
        options.log(`Python protocol error: ${String(error)}`);
      }
    });
    child.stderr.on("data", (data) => options.log(`[Python ${id}] ${String(data).trim()}`));
    child.on("error", (error) => { clearTimeout(timeout); onFailure(error); });
    child.on("exit", (code) => {
      clearTimeout(timeout);
      onFailure(new Error(`Python exited (${code})`));
      if (session.response) {
        session.response.end(JSON.stringify({ event: "fatal", message: `Python exited (${code})` }) + "\n");
      }
      sessions.delete(id);
    });
    return session;
  }

  const server = createServer(async (request, response) => {
    if (request.headers.authorization !== `Bearer ${token}`) {
      response.writeHead(401).end();
      return;
    }
    try {
      const parts: Buffer[] = [];
      let size = 0;
      for await (const chunk of request) {
        size += chunk.length;
        if (size > 8_388_608) throw new Error("Bridge request exceeds 8 MiB");
        parts.push(chunk);
      }
      const input = parts.length ? JSON.parse(Buffer.concat(parts).toString("utf8")) : {};
      const id = String(input.session || "desktop-readiness");
      const method = request.url;
      if (method === "/stop") {
        const session = sessions.get(id);
        if (session) {
          session.child.stdin.end(JSON.stringify({ method: "shutdown" }) + "\n");
          setTimeout(() => session.child.kill(), 6_000).unref();
        }
        response.end("{}");
        return;
      }
      const session = start(id, input.cwd);
      await session.ready;
      if (method === "/health" || method === "/start") {
        response.setHeader("content-type", "application/json");
        response.end(JSON.stringify({ event: "ready", engine: "AIAgent" }));
      } else if (method === "/interrupt") {
        session.child.stdin.write(JSON.stringify({ method: "interrupt" }) + "\n");
        response.end("{}");
      } else if (method === "/turn") {
        if (session.running) throw new Error("A turn is already running");
        session.running = true;
        session.response = response;
        response.writeHead(200, { "content-type": "application/x-ndjson" });
        response.flushHeaders();
        session.child.stdin.write(JSON.stringify({ ...input, method: "turn" }) + "\n");
        response.on("close", () => {
          if (session.response === response) {
            delete session.response;
            if (session.running) session.child.stdin.write('{"method":"interrupt"}\n');
          }
        });
      } else {
        response.writeHead(404).end();
      }
    } catch (error) {
      options.log(`Python bridge request failed: ${String(error)}`);
      if (!response.headersSent) response.writeHead(503, { "content-type": "application/json" });
      response.end(JSON.stringify({ error: String(error) }));
    }
  });
  await new Promise<void>((yes, no) => {
    server.once("error", no);
    server.listen(0, "127.0.0.1", yes);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Invalid Python bridge address");
  // Start imports before the first chat; health reports readiness through the existing UI.
  void start("desktop-readiness").ready.catch((error) => options.log(String(error)));
  return {
    environment: {
      ARKOS_PYTHON_BRIDGE_URL: `http://127.0.0.1:${address.port}`,
      ARKOS_PYTHON_BRIDGE_TOKEN: token,
    },
    async close() {
      closing = true;
      for (const session of sessions.values()) {
        session.child.stdin.end('{"method":"shutdown"}\n');
      }
      const killTimer = setTimeout(() => {
        for (const session of sessions.values()) session.child.kill();
      }, 6_000);
      killTimer.unref();
      server.closeAllConnections();
      await new Promise<void>((yes) => server.close(() => yes()));
    },
  };
}
