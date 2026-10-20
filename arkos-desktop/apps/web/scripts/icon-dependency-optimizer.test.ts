import { EventEmitter } from "node:events";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { ViteDevServer } from "vite";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  collectIconImports,
  createIconDependencyOptimizer,
  trimIconExports,
} from "./icon-dependency-optimizer";

const directories: string[] = [];
afterEach(async () => {
  for (const directory of directories.splice(0)) {
    if (!path.resolve(directory).startsWith(path.resolve(os.tmpdir()) + path.sep))
      throw new Error("Unexpected test directory");
    await fs.rm(directory, { recursive: true, force: true });
  }
});

describe("development icon dependency optimization", () => {
  it("collects named aliases and re-exports, ignoring type-only imports and comments", () => {
    const imports = collectIconImports(`
      import { IconCheck as Check, type TablerIcon } from '@tabler/icons-react';
      import type { IconType } from 'react-icons/si';
      export { SiGithub as GitHub } from 'react-icons/si';
      // import { SiOther } from 'react-icons/si';
    `);
    expect([...imports.get("@tabler/icons-react")!]).toEqual(["IconCheck"]);
    expect([...imports.get("react-icons/si")!]).toEqual(["SiGithub"]);
  });

  it.each([
    `import * as Icons from 'react-icons/pi';`,
    `const load = () => import('react-icons/pi');`,
    `export * from 'react-icons/pi';`,
  ])("retains the full API for namespace or dynamic access: %s", (source) => {
    const imports = collectIconImports(source);
    expect(imports.get("react-icons/pi")).toBeNull();
    expect(
      trimIconExports(
        "export function PiOne() {}",
        "/node_modules/react-icons/pi/index.mjs",
        imports,
      ),
    ).toBeNull();
  });

  it("makes unused generated React icon functions private so the optimizer can remove them", () => {
    const imports = collectIconImports(`import { PiOne } from 'react-icons/pi';`);
    const result = trimIconExports(
      "export function PiOne() {}\nexport function PiOther() {}",
      "C:\\repo\\node_modules\\react-icons\\pi\\index.mjs",
      imports,
    );
    expect(result).toContain("export function PiOne()");
    expect(result).toContain("\nfunction PiOther()");
    expect(result).not.toContain("export function PiOther");
    expect(trimIconExports("export function PiOne() {}", "/application.ts", imports)).toBeNull();
  });

  it("keeps the selected Tabler alias pointing at the original icon file", () => {
    const imports = collectIconImports(`import { IconNumber123 } from '@tabler/icons-react';`);
    const result = trimIconExports(
      `export { index as icons };\nexport { default as Icon123, default as IconNumber123 } from './icons/IconNumber123.mjs';\nexport { default as IconOther } from './icons/IconOther.mjs';`,
      "/node_modules/@tabler/icons-react/dist/esm/tabler-icons-react.mjs",
      imports,
    );
    expect(result).toContain("default as IconNumber123");
    expect(result).toContain("from './icons/IconNumber123.mjs'");
    expect(result).not.toContain("IconOther");
    expect(result).not.toContain("index as icons");
    expect(result).not.toContain("default as Icon123,");
  });

  it("invalidates optimized dependencies when live editing adds an icon", async () => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), "arkos-icon-optimizer-"));
    directories.push(root);
    const file = path.join(root, "component.tsx");
    await fs.writeFile(file, `import { IconCheck } from '@tabler/icons-react';`);
    const optimizer = await createIconDependencyOptimizer(root);
    const watcher = new EventEmitter();
    const restart = vi.fn(async () => {});
    const logger = { error: vi.fn() };
    optimizer.watchPlugin.configureServer({
      watcher,
      restart,
      config: { logger },
    } as unknown as ViteDevServer);
    await fs.writeFile(file, `import { IconCheck, IconX } from '@tabler/icons-react';`);
    watcher.emit("all", "change", file);
    await vi.waitFor(() => expect(restart).toHaveBeenCalledOnce());
    expect(logger.error).not.toHaveBeenCalled();
    const next = await createIconDependencyOptimizer(root);
    expect(next.optimizerPlugin.name).not.toBe(optimizer.optimizerPlugin.name);
  });
});
