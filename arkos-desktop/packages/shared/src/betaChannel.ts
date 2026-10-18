// FILE: betaChannel.ts
// Purpose: Shared constants and types for the Stable ↔ Arkos Beta handoff flow.
// Layer: Shared contracts (consumed by desktop main, server, and web settings UI)

import { Schema } from "effect";

/** Beta's data home; stable writes the import marker here, the beta server consumes it. */
export const ARKOS_BETA_HOME_DIR_NAME = ".arkos-beta";
export const BETA_IMPORT_REQUEST_FILE_NAME = "import-requested.json";
export const BETA_IMPORT_RESULT_FILE_NAME = "import-result.json";

/**
 * electron-builder NSIS `guid` for beta builds. The uninstall registry key is
 * the raw GUID (no braces — see app-builder-lib NsisTarget / multiUser.nsh).
 */
export const ARKOS_BETA_WINDOWS_INSTALLER_GUID = "a8e63b48-d4f3-4db5-9e12-368107afe65d";

/**
 * Optional release page URLs surfaced in settings. Leave unset to hide the
 * download links; there is no built-in repository default.
 */
export const ARKOS_BETA_RELEASES_URL_ENV = "ARKOS_BETA_RELEASES_URL";
export const ARKOS_STABLE_RELEASES_URL_ENV = "ARKOS_STABLE_RELEASES_URL";

/** electron-builder NSIS `guid` for stable (production) builds. */
export const ARKOS_STABLE_WINDOWS_INSTALLER_GUID = "368107a8-afe6-5db5-ab3b-d4f331684868";

/**
 * Optional GitHub-compatible releases API probed for the newest `v*-beta.N`
 * tag when `ARKOS_BETA_FEED_URL` is not set.
 */
export const ARKOS_BETA_RELEASES_API_URL_ENV = "ARKOS_BETA_RELEASES_API_URL";

/**
 * Environment overrides for the beta install flow. `ARKOS_BETA_HOME` moves the
 * beta data home everywhere it is resolved (stable's import marker, beta's own
 * base dir, the running-probe). `ARKOS_BETA_FEED_URL` points at a base URL
 * serving `beta-mac.yml` plus the files it lists; `ARKOS_BETA_INSTALL_DIR` and
 * `ARKOS_BETA_USER_DATA` relocate the app bundle and its Electron profile.
 */
export const ARKOS_BETA_HOME_ENV = "ARKOS_BETA_HOME";
export const ARKOS_BETA_FEED_URL_ENV = "ARKOS_BETA_FEED_URL";
export const ARKOS_BETA_INSTALL_DIR_ENV = "ARKOS_BETA_INSTALL_DIR";
export const ARKOS_BETA_USER_DATA_ENV = "ARKOS_BETA_USER_DATA";

/**
 * Set by stable when it launches beta, so "Switch back to Arkos" reopens that
 * exact stable app with its own data home instead of guessing install paths.
 */
export const ARKOS_STABLE_EXECUTABLE_ENV = "ARKOS_STABLE_EXECUTABLE";
export const ARKOS_STABLE_HOME_ENV = "ARKOS_STABLE_HOME";

/** Tag shape of a beta release: `v<version>-beta.<N>`. */
export const BETA_RELEASE_TAG_PATTERN = /^v\d+\.\d+\.\d+-beta\.\d+$/;

export const BetaImportRequest = Schema.Struct({
  version: Schema.Literal(1),
  requestedAt: Schema.String,
  /** Absolute path of the requesting install's Arkos home (e.g. `~/.arkos`). */
  sourceHomeDir: Schema.String,
});
export type BetaImportRequest = typeof BetaImportRequest.Type;

export const BetaImportResult = Schema.Struct({
  version: Schema.Literal(1),
  completedAt: Schema.String,
  ok: Schema.Boolean,
  error: Schema.optional(Schema.String),
});
export type BetaImportResult = typeof BetaImportResult.Type;

export const decodeBetaImportRequest = Schema.decodeUnknownSync(BetaImportRequest);
export const decodeBetaImportResult = Schema.decodeUnknownSync(BetaImportResult);
