import { describe, expect, it } from "vitest";
import { Schema } from "effect";
import { ProviderSendTurnInput, ProviderSessionStartInput } from "./provider";

const decodeProviderSessionStartInput = Schema.decodeUnknownSync(ProviderSessionStartInput);
const decodeProviderSendTurnInput = Schema.decodeUnknownSync(ProviderSendTurnInput);

describe("ProviderSessionStartInput", () => {
  it("accepts explicit per-thread computer control provisioning", () => {
    const parsed = decodeProviderSessionStartInput({
      threadId: "thread-computer",
      provider: "arkos",
      enableComputerControl: true,
      runtimeMode: "full-access",
    });
    expect(parsed.enableComputerControl).toBe(true);
  });

  it("rejects payloads without runtime mode", () => {
    expect(() =>
      decodeProviderSessionStartInput({
        threadId: "thread-1",
        provider: "arkos",
      }),
    ).toThrow();
  });
});

describe("ProviderSendTurnInput", () => {
  it("accepts arkos modelSelection", () => {
    const parsed = decodeProviderSendTurnInput({
      threadId: "thread-1",
      modelSelection: {
        provider: "arkos",
        model: "engine-default",
        options: {},
      },
    });
    expect(parsed.modelSelection?.provider).toBe("arkos");
    expect(parsed.modelSelection?.model).toBe("engine-default");
  });
});
