import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  findBrandIdentityViolations,
  findVisualBrandAssetViolations,
  readTrackedFiles,
} from "./check-brand-identity";

const characters = (...codes: number[]): string => String.fromCharCode(...codes);
const shortName = characters(116, 51);
const firstName = `${shortName}${characters(99, 111, 100, 101)}`;
const secondName = characters(100, 112, 99, 111, 100, 101);
const companyDisplayName = `${characters(84, 51)} ${characters(84, 111, 111, 108, 115)}`;
const fixtureBundleDomain = characters(99, 111, 109, 46, 115, 121, 110, 97, 114, 97);
const legalNotice = `Copyright (c) 2026 ${companyDisplayName} Inc.`;

describe("brand identity guard", () => {
  it("scans owned files while ignoring initialized and absent gitlinks", () => {
    const cwd = mkdtempSync(join(tmpdir(), "arkos-brand-"));
    const git = (...args: string[]) => execFileSync("git", args, { cwd, encoding: "utf8" }).trim();
    try {
      git("init", "--quiet");
      const path = "source with spaces.ts";
      writeFileSync(join(cwd, path), `const value = "${secondName}:state";`);
      git("add", "--", path);
      const oid = git("hash-object", "-w", path);
      git("update-index", "--add", "--cacheinfo", `160000,${oid},nested`);
      git("update-index", "--add", "--cacheinfo", `160000,${oid},absent`);
      mkdirSync(join(cwd, "nested"));
      writeFileSync(join(cwd, "nested", "outside.ts"), firstName);

      const files = readTrackedFiles(cwd);
      expect(files.map((file) => file.path)).toEqual([path]);
      expect(
        findBrandIdentityViolations(
          files.map((file) => ({ ...file, contents: Buffer.from(file.contents).toString("utf8") })),
        ),
      ).toHaveLength(1);

      // Deleted source files are absent from the resulting working tree.
      rmSync(join(cwd, path));
      expect(readTrackedFiles(cwd)).toEqual([]);
    } finally {
      rmSync(cwd, { recursive: true, force: true });
    }
  });

  it("detects retired names in paths and text", () => {
    const violations = findBrandIdentityViolations([
      { path: `docs/${firstName}.md`, contents: "Arkos" },
      { path: "source.ts", contents: `const value = "${secondName}:state";` },
    ]);
    expect(violations).toHaveLength(2);
  });

  it("does not match ordinary numeric type names or canonical Arkos text", () => {
    expect(
      findBrandIdentityViolations([
        { path: "source.ts", contents: "const value = new Uint32Array(); // Arkos" },
      ]),
    ).toEqual([]);
  });

  it("rejects invented project websites and malformed repository documentation links", () => {
    const repository = "https://github.com/example-org/Arkos";
    for (const contents of [
      `https://${"arkos.com"}`,
      `https://${"www.try"}${"arkos.app/docs"}`,
      `${repository}/workflows/worktrees`,
    ]) {
      expect(findBrandIdentityViolations([{ path: "source.ts", contents }])).toHaveLength(1);
    }
    expect(
      findBrandIdentityViolations([
        { path: "source.ts", contents: "https://github.com/example-org/Arkos" },
        { path: "source.ts", contents: "https://arkos.example.test" },
      ]),
    ).toEqual([]);
  });

  it("allows the exact legal attribution once in the preserved notice", () => {
    expect(
      findBrandIdentityViolations([{ path: "licenses/inherited-MIT.txt", contents: legalNotice }]),
    ).toEqual([]);
    expect(
      findBrandIdentityViolations([{ path: "docs/license-copy.md", contents: legalNotice }]),
    ).toHaveLength(1);
    expect(
      findBrandIdentityViolations([
        { path: "licenses/inherited-MIT.txt", contents: `${legalNotice}\n${legalNotice}` },
      ]),
    ).toHaveLength(1);
  });

  it("allows only the two reviewed cubic expressions in the native patch", () => {
    const path = "apps/desktop/patches/cua-driver/0001-arkos-native.patch";
    const firstExpression = `+                            + ${shortName} * self.to.0`;
    const expressions = [firstExpression, firstExpression.replace("self.to.0", "self.to.1")];
    expect(findBrandIdentityViolations([{ path, contents: expressions.join("\n") }])).toEqual([]);
    for (const contents of [
      `${firstExpression}\n${firstExpression}`,
      firstExpression.replace("self.to.0", "self.from.0"),
      `${firstExpression} // ${firstName}`,
      `${expressions.join("\n")}\n+ ${secondName}`,
    ]) {
      expect(findBrandIdentityViolations([{ path, contents }])).toHaveLength(1);
    }
    expect(
      findBrandIdentityViolations([
        { path: "apps/desktop/patches/cua-driver/other.patch", contents: expressions.join("\n") },
      ]),
    ).toHaveLength(2);
  });

  it("rejects retired bundle identities in code, fixtures, and evidence", () => {
    const bundleId = `${fixtureBundleDomain}.cua-fixture`;
    expect(
      findBrandIdentityViolations([
        { path: "apps/desktop/src/main.ts", contents: bundleId },
        { path: "apps/desktop/src/cuaFixtures/new.ts", contents: bundleId },
        { path: "scripts/computer-use-fixtures/new.mjs", contents: bundleId },
        { path: "apps/server/src/computer/new.test.ts", contents: bundleId },
        { path: "docs/computer-use-cua/evidence/new-report.json", contents: bundleId },
        { path: "scripts/computer-use-fixtures/build-canary.mjs", contents: bundleId },
        { path: "apps/desktop/src/cuaFixtures/electron.ts", contents: `${bundleId}-external` },
      ]),
    ).toHaveLength(7);
  });

  it("requires user-facing raster assets to match a visually approved digest", () => {
    const approvedContents = new TextEncoder().encode("approved Arkos screenshot");
    const approvedDigest = "6a5b678afcada2039d473a0a88285b3ae5a6fc5db6e013a720b60c52ce811883";
    const approvedDigests = new Map([["screenshot.jpeg", approvedDigest]]);

    expect(
      findVisualBrandAssetViolations(
        [{ path: "screenshot.jpeg", contents: approvedContents }],
        approvedDigests,
      ),
    ).toEqual([]);
    expect(
      findVisualBrandAssetViolations(
        [{ path: "screenshot.jpeg", contents: new TextEncoder().encode("changed") }],
        approvedDigests,
      ),
    ).toHaveLength(1);
    expect(findVisualBrandAssetViolations([], approvedDigests)).toHaveLength(1);
  });
});
