// FILE: modelFavorites.migration.test.ts
// Purpose: Verifies Kilo favorite models survive the provider migration to OpenCode.

import { describe, expect, it } from "vitest";

import { FAVORITE_MODEL_STORAGE_KEYS, migrateLegacyKiloFavoriteModelSlugs } from "./modelFavorites";

const LEGACY_KILO_KEY = "arkos:kilo-favourite-models:v1";

function makeMemoryStorage(initial: Record<string, string>): Storage {
  const values = new Map(Object.entries(initial));
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}

describe("migrateLegacyKiloFavoriteModelSlugs", () => {

});
