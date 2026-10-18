// FILE: check-brand-identity.ts
// Purpose: Prevents retired first-party identities from returning to tracked files.

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const characters = (...codes: number[]): string => String.fromCharCode(...codes);
const retiredShortName = characters(116, 51);
const retiredFirstName = `${retiredShortName}${characters(99, 111, 100, 101)}`;
const retiredCompanyName = `${retiredShortName}${characters(116, 111, 111, 108, 115)}`;
const retiredSecondName = characters(100, 112, 99, 111, 100, 101);
const retiredPredecessorName = characters(99, 111, 100, 101, 116, 104, 105, 110, 103);
const incorrectBundleDomain = characters(99, 111, 109, 46, 115, 121, 110, 97, 114, 97);

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const joinedWithOptionalSeparator = (left: string, right: string): string =>
  `${escapeRegExp(left)}[\\s._/@:-]*${escapeRegExp(right)}`;

const forbiddenPatterns = [
  // No project website has been configured. A rename must not invent one.
  /https?:\/\/(?:www\.)?(?:try)?arkos\.(?:com|dev|app|ai|sh)(?:[/:?#\s"']|$)/i,
  // Repository documentation links for the product name are not a published surface.
  /https?:\/\/github\.com\/[^/\s]+\/[Aa]rkos\/(?:getting-started|workflows|reference)(?:\/|$)/i,
  new RegExp(
    joinedWithOptionalSeparator(retiredShortName, retiredFirstName.slice(retiredShortName.length)),
    "i",
  ),
  new RegExp(
    joinedWithOptionalSeparator(
      retiredShortName,
      retiredCompanyName.slice(retiredShortName.length),
    ),
    "i",
  ),
  new RegExp(
    joinedWithOptionalSeparator(retiredSecondName.slice(0, 2), retiredSecondName.slice(2)),
    "i",
  ),
  new RegExp(escapeRegExp(retiredPredecessorName), "i"),
  new RegExp(`@${escapeRegExp(retiredCompanyName)}`, "i"),
  new RegExp(
    `(?:^|[\\s"'\\x60./:@_-])${escapeRegExp(retiredShortName)}(?:$|[\\s"'\\x60./:@_-])`,
    "i",
  ),
  new RegExp(escapeRegExp(incorrectBundleDomain), "i"),
  ...[
    characters(115, 121, 110, 97, 114, 97),
    characters(115, 121, 97, 110, 97, 114, 97),
    characters(99, 121, 97, 110, 97, 114, 97),
    characters(115, 121, 110, 97, 116, 97),
  ].map((name) => new RegExp(escapeRegExp(name), "i")),
] as const;

interface ApprovedIdentityLine {
  readonly path: string;
  readonly line: string;
  readonly markdownSection?: string;
}

const approvedIdentityLines: readonly ApprovedIdentityLine[] = [
  // These two terms are the cubic time coefficient in the reviewed native
  // patch. Keep the patch and its recorded checksum unchanged.
  ...[0, 1].map((axis) => ({
    path: "apps/desktop/patches/cua-driver/0001-arkos-native.patch",
    line: `+                            + ${retiredShortName} * self.to.${axis}`,
  })),
];

// Raster images cannot be searched for embedded text. Keep the user-facing
// screenshots behind reviewed digests so changing either one requires another
// explicit visual identity audit instead of silently bypassing this guard.
const approvedVisualAssetDigests = new Map<string, string>([
  [
    "assets/prod/black-universal-1024.png",
    "1e50bf53afd89d79554e78881f4fe61c2f14337878dce0d64d699236f706b9cc",
  ],
  [
    "assets/dev/blueprint-universal-1024.png",
    "1e50bf53afd89d79554e78881f4fe61c2f14337878dce0d64d699236f706b9cc",
  ],
  [
    "assets/beta/beta-universal-1024.png",
    "6a7f5af32aaa6a2bccc007d3307eea9628e67ece085bf82d9d2fdfddac4e180d",
  ],
  ["apps/web/public/arkos.png", "1e50bf53afd89d79554e78881f4fe61c2f14337878dce0d64d699236f706b9cc"],
  [
    "assets/prod/readme-split-view-dark.png",
    "f4c3a1eebf298b4b46ec5fd0e2c841e946ffa004a9c861678b521879e060d2df",
  ],
  [
    "assets/prod/readme-appearance-dark.png",
    "8d151fe29a68635d961f1ae13ee53b32a5aaf6fb59a58d8356b8036c1c70ddaa",
  ],
  [
    "apps/desktop/resources/app-icon-windows.ico",
    "6c3db0b670e682efad1c277e6302b5e0ad67466ff19a51d27d19850904f39044",
  ],
]);

export interface BrandIdentityFile {
  readonly path: string;
  readonly contents: string;
}

export interface BrandIdentityViolation {
  readonly path: string;
  readonly line: number | null;
  readonly text: string;
}

export interface BrandIdentityBinaryFile {
  readonly path: string;
  readonly contents: Uint8Array;
}

function containsForbiddenIdentity(value: string): boolean {
  return forbiddenPatterns.some((pattern) => pattern.test(value));
}

function findApprovedIdentityLine(
  path: string,
  line: string,
  markdownSection: string | null,
  consumedLines: ReadonlySet<number>,
): number | null {
  const index = approvedIdentityLines.findIndex(
    (approved, candidateIndex) =>
      !consumedLines.has(candidateIndex) &&
      approved.path === path &&
      approved.line === line.trim() &&
      (approved.markdownSection === undefined || approved.markdownSection === markdownSection),
  );
  return index === -1 ? null : index;
}

export function findBrandIdentityViolations(
  files: readonly BrandIdentityFile[],
): BrandIdentityViolation[] {
  const violations: BrandIdentityViolation[] = [];
  for (const file of files) {
    if (containsForbiddenIdentity(file.path)) {
      violations.push({ path: file.path, line: null, text: file.path });
    }
    const consumedLines = new Set<number>();
    let markdownSection: string | null = null;
    for (const [index, line] of file.contents.split(/\r?\n/).entries()) {
      if (/^#{1,2}\s+/.test(line)) markdownSection = line.trim();
      if (!containsForbiddenIdentity(line)) continue;
      const approvedLine = findApprovedIdentityLine(
        file.path,
        line,
        markdownSection,
        consumedLines,
      );
      if (approvedLine !== null) {
        consumedLines.add(approvedLine);
        continue;
      }
      violations.push({ path: file.path, line: index + 1, text: line.trim() });
    }
  }
  return violations;
}

export function findVisualBrandAssetViolations(
  files: readonly BrandIdentityBinaryFile[],
  approvedDigests: ReadonlyMap<string, string> = approvedVisualAssetDigests,
): BrandIdentityViolation[] {
  const filesByPath = new Map(files.map((file) => [file.path, file]));
  const violations: BrandIdentityViolation[] = [];
  for (const [path, approvedDigest] of approvedDigests) {
    const file = filesByPath.get(path);
    if (!file) {
      violations.push({
        path,
        line: null,
        text: "Required visual brand asset is missing.",
      });
      continue;
    }
    const digest = createHash("sha256").update(file.contents).digest("hex");
    if (digest !== approvedDigest) {
      violations.push({
        path,
        line: null,
        text: "Visual brand asset changed; perform a visual identity review before approving it.",
      });
    }
  }
  return violations;
}

export function readTrackedFiles(cwd = process.cwd()): BrandIdentityBinaryFile[] {
  const entries = execFileSync("git", ["ls-files", "--stage", "-z"], { cwd, encoding: "utf8" })
    .split("\0")
    .filter(Boolean);
  // Gitlinks name another repository, not a file owned by this checkout. They may
  // exist as directories or be absent when submodules have not been initialized.
  const paths = entries
    .filter((entry) => !entry.startsWith("160000 "))
    .map((entry) => entry.slice(entry.indexOf("\t") + 1))
    // Audit the current working tree, including intentional file removals.
    .filter((path) => existsSync(resolve(cwd, path)));
  return paths.map((path) => ({ path, contents: readFileSync(resolve(cwd, path)) }));
}

function main(): void {
  const trackedFiles = readTrackedFiles();
  const searchableFiles = trackedFiles.map((file) => ({
    path: file.path,
    contents: file.contents.includes(0) ? "" : Buffer.from(file.contents).toString("utf8"),
  }));
  const violations = [
    ...findBrandIdentityViolations(searchableFiles),
    ...findVisualBrandAssetViolations(trackedFiles),
  ];
  if (violations.length === 0) {
    console.log("Arkos identity check passed.");
    return;
  }

  console.error("Retired first-party identity found:");
  for (const violation of violations) {
    const location =
      violation.line === null ? violation.path : `${violation.path}:${violation.line}`;
    console.error(`- ${location}: ${violation.text}`);
  }
  process.exitCode = 1;
}

if (import.meta.main) main();
