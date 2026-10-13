import * as FS from "node:fs";
import * as OS from "node:os";
import * as Path from "node:path";

import { describe, expect, it } from "vitest";

import {
  acknowledgeArkosStorageSnapshot,
  readArkosStorageSnapshot,
  ARKOS_STORAGE_SNAPSHOT_MAX_BYTES,
  validateArkosStorageSnapshot,
} from "./desktopStorageMigration";

const snapshot = () => ({
  version: 1 as const,
  exportedAt: "2026-07-09T00:00:00.000Z",
  entries: {
    "arkos:theme": "dark",
    "arkos.openUsage.enabled": "true",
  },
});

describe("desktopStorageMigration", () => {
  it("reads a legacy snapshot and removes it after acknowledgement", async () => {
    const directory = FS.mkdtempSync(Path.join(OS.tmpdir(), "arkos-storage-migration-"));
    const target = Path.join(directory, "snapshot.json");
    try {
      FS.writeFileSync(target, `${JSON.stringify(snapshot())}\n`);
      expect(readArkosStorageSnapshot(target)).toEqual(snapshot());

      await acknowledgeArkosStorageSnapshot(target);
      expect(readArkosStorageSnapshot(target)).toBeNull();
    } finally {
      FS.rmSync(directory, { recursive: true, force: true });
    }
  });

  it("rejects malformed, disallowed, and oversized snapshots", () => {
    expect(validateArkosStorageSnapshot({ version: 1 })).toBeNull();
    expect(
      validateArkosStorageSnapshot({
        ...snapshot(),
        entries: { "foreign:theme": "dark" },
      }),
    ).toBeNull();
    expect(
      validateArkosStorageSnapshot({
        ...snapshot(),
        entries: { "arkos:large": "x".repeat(ARKOS_STORAGE_SNAPSHOT_MAX_BYTES) },
      }),
    ).toBeNull();
  });

  it("accepts renderer snapshots containing large composer drafts", () => {
    const largeDraft = "x".repeat(2 * 1024 * 1024);

    expect(
      validateArkosStorageSnapshot({
        ...snapshot(),
        entries: { "arkos:composer-drafts:v1": largeDraft },
      })?.entries["arkos:composer-drafts:v1"],
    ).toBe(largeDraft);
  });

  it("treats missing and malformed files as absent", () => {
    const directory = FS.mkdtempSync(Path.join(OS.tmpdir(), "arkos-storage-migration-"));
    const target = Path.join(directory, "snapshot.json");
    try {
      expect(readArkosStorageSnapshot(target)).toBeNull();
      FS.writeFileSync(target, "not json");
      expect(readArkosStorageSnapshot(target)).toBeNull();
    } finally {
      FS.rmSync(directory, { recursive: true, force: true });
    }
  });
});
