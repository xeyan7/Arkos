import type { ChildProcess } from "node:child_process";
import * as FS from "node:fs";
import * as OS from "node:os";
import * as Path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyWindowsShellAppUserModel,
  ensureWindowsShellAppUserModelHelper,
  windowsShellAppUserModelHelperName,
  WINDOWS_SHELL_HELPER_TIMEOUT_MS,
} from "./windowsShellAppUserModel";

const execFile = vi.hoisted(() =>
  vi.fn<
    (
      file: string,
      args: readonly string[],
      options: { windowsHide: boolean; timeout: number },
      callback: (error: Error | null, stdout: string, stderr: string) => void,
    ) => ChildProcess
  >(),
);
vi.mock("node:child_process", () => ({ execFile }));
vi.mock("node:fs", async (original) => {
  const fs = await original<typeof import("node:fs")>();
  return {
    ...fs,
    existsSync: (path: FS.PathLike) => String(path).endsWith("csc.exe") || fs.existsSync(path),
  };
});

let cacheDirectory: string;
beforeEach(() => {
  execFile.mockReset();
  cacheDirectory = FS.mkdtempSync(Path.join(OS.tmpdir(), "arkos-shell-async-"));
});
afterEach(() => {
  const tempRoot = Path.resolve(OS.tmpdir()) + Path.sep;
  if (!Path.resolve(cacheDirectory).startsWith(tempRoot))
    throw new Error("Unexpected test directory");
  FS.rmSync(cacheDirectory, { recursive: true, force: true });
});
const input = {
  appId: "Arkos.Dev",
  iconPath: "test.ico",
  relaunchCommand: "electron",
  displayName: "Arkos Dev",
  shortcutPaths: ["test.lnk"],
  hwnd: 42n,
};

describe("asynchronous Windows shell integration", () => {
  it("shares a cold compilation without blocking the caller and reuses the built helper", async () => {
    let finish!: () => void;
    execFile.mockImplementation((_file, args, _options, callback) => {
      finish = () => {
        FS.writeFileSync(args.find((arg) => arg.startsWith("/out:"))!.slice(5), "fixture");
        callback(null, "", "");
      };
      return {} as ChildProcess;
    });
    const first = ensureWindowsShellAppUserModelHelper(cacheDirectory);
    const second = ensureWindowsShellAppUserModelHelper(cacheDirectory);
    expect(second).toBe(first);
    await vi.waitFor(() => expect(execFile).toHaveBeenCalledTimes(1));
    let settled = false;
    void first.then(() => {
      settled = true;
    });
    await new Promise((resolve) => setImmediate(resolve));
    expect(settled).toBe(false);
    finish();
    const helper = await first;
    expect(await second).toBe(helper);
    expect(await ensureWindowsShellAppUserModelHelper(cacheDirectory)).toBe(helper);
    expect(execFile).toHaveBeenCalledTimes(1);
  });

  it("keeps Electron's event loop available until Explorer finishes and preserves its arguments", async () => {
    FS.writeFileSync(Path.join(cacheDirectory, windowsShellAppUserModelHelperName()), "fixture");
    let finish!: () => void;
    execFile.mockImplementation((_file, _args, _options, callback) => {
      finish = () => callback(null, "", "");
      return {} as ChildProcess;
    });
    const pending = applyWindowsShellAppUserModel(input, cacheDirectory);
    await vi.waitFor(() => expect(execFile).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setImmediate(resolve));
    expect(execFile.mock.calls[0]?.[1]).toEqual([
      "apply",
      input.appId,
      "test.ico,0",
      input.relaunchCommand,
      input.displayName,
      "42",
      "test.lnk",
    ]);
    expect(execFile.mock.calls[0]?.[2]).toMatchObject({
      windowsHide: true,
      timeout: WINDOWS_SHELL_HELPER_TIMEOUT_MS,
    });
    finish();
    await pending;
  });

  it("clears a failed compilation so a later icon update can retry", async () => {
    execFile.mockImplementationOnce((_file, _args, _options, callback) => {
      queueMicrotask(() => callback(new Error("compiler failed"), "", "compile failure"));
      return {} as ChildProcess;
    });
    await expect(ensureWindowsShellAppUserModelHelper(cacheDirectory)).rejects.toThrow(
      "compile failure",
    );
    execFile.mockImplementationOnce((_file, args, _options, callback) => {
      FS.writeFileSync(args.find((arg) => arg.startsWith("/out:"))!.slice(5), "fixture");
      queueMicrotask(() => callback(null, "", ""));
      return {} as ChildProcess;
    });
    await expect(ensureWindowsShellAppUserModelHelper(cacheDirectory)).resolves.toContain(
      windowsShellAppUserModelHelperName(),
    );
    expect(execFile).toHaveBeenCalledTimes(2);
  });
});
