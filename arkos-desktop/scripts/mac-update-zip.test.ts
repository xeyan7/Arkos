// FILE: mac-update-zip.test.ts
// Purpose: Locks down macOS update zip validation and latest-mac.yml patching.
// Layer: Release/build tests
// Depends on: scripts/lib/mac-update-zip.ts.

import { assert, describe, it } from "@effect/vitest";

import {
  assertMacUpdateManifestZipMetadata,
  buildMacUpdateZipSymlinkEntries,
  isZipInfoSymlink,
  resolveMacUpdateManifestFileNames,
  resolveSingleMacUpdateZipFileName,
  resolveSingleTopLevelMacAppBundle,
  updateMacUpdateManifestZipEntry,
} from "./lib/mac-update-zip.ts";

describe("mac-update-zip", () => {
  it("detects symlink entries from unzip verbose metadata", () => {
    assert.equal(
      isZipInfoSymlink(
        `  Unix file attributes (120755 octal):            lrwxr-xr-x
  MS-DOS file attributes (00 hex):                none
`,
      ),
      true,
    );
    assert.equal(
      isZipInfoSymlink(
        `  Unix file attributes (100755 octal):            -rwxr-xr-x
  MS-DOS file attributes (00 hex):                none
`,
      ),
      false,
    );
  });

  it("builds Electron framework symlink paths for the top-level app bundle", () => {
    assert.deepStrictEqual(buildMacUpdateZipSymlinkEntries("Arkos.app"), [
      "Arkos.app/Contents/Frameworks/Electron Framework.framework/Electron Framework",
      "Arkos.app/Contents/Frameworks/Electron Framework.framework/Helpers",
      "Arkos.app/Contents/Frameworks/Electron Framework.framework/Libraries",
      "Arkos.app/Contents/Frameworks/Electron Framework.framework/Resources",
      "Arkos.app/Contents/Frameworks/Electron Framework.framework/Versions/Current",
    ]);
  });

  it("resolves exactly one top-level .app from update zip entries", () => {
    assert.equal(
      resolveSingleTopLevelMacAppBundle([
        "__MACOSX/Arkos.app/Contents/Info.plist",
        "Arkos.app/Contents/Info.plist",
        "Arkos.app/Contents/MacOS/Arkos",
      ]),
      "Arkos.app",
    );

    assert.throws(
      () =>
        resolveSingleTopLevelMacAppBundle([
          "Arkos.app/Contents/Info.plist",
          "Other.app/Contents/Info.plist",
        ]),
      /Expected one top-level \.app bundle/,
    );
  });

  it("resolves exactly one macOS update zip artifact", () => {
    assert.equal(
      resolveSingleMacUpdateZipFileName([
        "Arkos-0.1.5-arm64.dmg",
        "Arkos-0.1.5-arm64.zip",
        "latest-mac.yml",
      ]),
      "Arkos-0.1.5-arm64.zip",
    );

    assert.throws(
      () => resolveSingleMacUpdateZipFileName(["Arkos-0.1.5-arm64.zip", "Arkos-0.1.5-x64.zip"]),
      /Expected one macOS update zip artifact/,
    );
  });

  it("requires at least one macOS update manifest", () => {
    assert.deepStrictEqual(
      resolveMacUpdateManifestFileNames([
        "Arkos-0.1.5-arm64.dmg",
        "Arkos-0.1.5-arm64.zip",
        "latest-mac.yml",
      ]),
      ["latest-mac.yml"],
    );

    assert.throws(
      () => resolveMacUpdateManifestFileNames(["Arkos-0.1.5-arm64.dmg"]),
      /Expected at least one macOS update manifest/,
    );
  });

  it("allows a missing manifest only for an explicitly scripted-update artifact", () => {
    const artifacts = ["Arkos-Cua-0.8.4-arm64.zip"];
    assert.deepStrictEqual(resolveMacUpdateManifestFileNames(artifacts, { required: false }), []);
    assert.throws(() => resolveMacUpdateManifestFileNames(artifacts, { required: true }));
    assert.throws(() => resolveMacUpdateManifestFileNames(artifacts));
  });

  it("still returns present manifests for validation when a feed is optional", () => {
    assert.deepStrictEqual(
      resolveMacUpdateManifestFileNames(["Arkos-Cua-0.8.4-arm64.zip", "latest-mac.yml"], {
        required: false,
      }),
      ["latest-mac.yml"],
    );
  });

  it.each([false, true])(
    "updates zip metadata and preserves dmg fields (blockmaps: %s)",
    (withBlockmaps) => {
      const manifest = `version: 0.1.4
files:
  - url: Arkos-0.1.4-arm64.zip
    sha512: oldzip
    size: 100
${withBlockmaps ? "    blockMapSize: 50\n" : ""}  - url: Arkos-0.1.4-arm64.dmg
    sha512: olddmg
    size: 200
${withBlockmaps ? "    blockMapSize: 75\n" : ""}path: 'Arkos-0.1.4-arm64.zip'
sha512: oldzip
releaseDate: '2026-06-07T12:00:00.000Z'
`;

      const updated = updateMacUpdateManifestZipEntry(manifest, "Arkos-0.1.4-arm64.zip", {
        sha512: "newzip",
        size: 12345,
      });

      assert.equal(
        updated,
        `version: 0.1.4
files:
  - url: Arkos-0.1.4-arm64.zip
    sha512: newzip
    size: 12345
  - url: Arkos-0.1.4-arm64.dmg
    sha512: olddmg
    size: 200
${withBlockmaps ? "    blockMapSize: 75\n" : ""}path: 'Arkos-0.1.4-arm64.zip'
sha512: newzip
releaseDate: '2026-06-07T12:00:00.000Z'
`,
      );
    },
  );

  it("rejects manifests missing the target zip entry", () => {
    assert.throws(
      () =>
        updateMacUpdateManifestZipEntry(
          `version: 0.1.4
files:
  - url: Arkos-0.1.4-arm64.dmg
    sha512: olddmg
    size: 200
releaseDate: '2026-06-07T12:00:00.000Z'
`,
          "Arkos-0.1.4-arm64.zip",
          {
            sha512: "newzip",
            size: 12345,
          },
        ),
      /Could not update Arkos-0.1.4-arm64.zip entry/,
    );
  });

  it("validates manifest metadata after zip repack", () => {
    const manifest = `version: 0.1.5
files:
  - url: Arkos-0.1.5-arm64.zip
    sha512: newzip
    size: 12345
path: Arkos-0.1.5-arm64.zip
sha512: newzip
releaseDate: '2026-06-07T12:00:00.000Z'
`;
    const metadata = { sha512: "newzip", size: 12345 };

    assert.deepStrictEqual(
      assertMacUpdateManifestZipMetadata(manifest, "Arkos-0.1.5-arm64.zip", metadata),
      {
        manifestHasZipPath: true,
        manifestHasZipSha: true,
        manifestHasZipSize: true,
      },
    );
  });
});
