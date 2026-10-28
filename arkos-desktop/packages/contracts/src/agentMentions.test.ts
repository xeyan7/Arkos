import { describe, expect, it } from "vitest";
import {
  getAgentMentionAliases,
  getAgentMentionAutocompleteAliases,
  isValidAgentAlias,
  resolveAgentAlias,
} from "./agentMentions";

describe("agentMentions", () => {
  it("returns no aliases when none are registered for arkos", () => {
    expect(getAgentMentionAutocompleteAliases("arkos")).toEqual([]);
    expect(getAgentMentionAliases("arkos")).toEqual([]);
    expect(resolveAgentAlias("anything", "arkos")).toBeNull();
    expect(isValidAgentAlias("anything", "arkos")).toBe(false);
  });
});
