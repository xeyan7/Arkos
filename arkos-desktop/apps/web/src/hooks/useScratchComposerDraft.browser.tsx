import { ThreadId } from "@arkos/contracts";
import { flushSync } from "react-dom";
import { beforeEach, expect, it } from "vitest";
import { renderHook } from "vitest-browser-react";
import type { AppSettings } from "../appSettings";
import { useComposerDraftStore } from "../composerDraftStore";
import { resetComposerDraftStore } from "../composerDraftStoreTestFixtures";
import { useScratchComposerDraft } from "./useScratchComposerDraft";
beforeEach(() => resetComposerDraftStore());
it("keeps custom provider instances distinct while restoring and changing a scratch model", async () => {
    const settings = {
        providerInstances: {
            codex_work: { driver: "arkos", displayName: "Work", enabled: true },
            codex_personal: { driver: "arkos", displayName: "Personal", enabled: true },
        },
    } satisfies Pick<AppSettings, "providerInstances">;
    useComposerDraftStore
        .getState()
        .setModelSelectionAndSticky(ThreadId.makeUnsafe("previous-chat"), {
        provider: "arkos",
        instanceId: "codex_work",
        model: "gpt-5.4",
        options: { reasoningEffort: "high" },
    });
    const hook = await renderHook(() => useScratchComposerDraft({ defaultProvider: "arkos", settings }));
    try {
        expect(hook.result.current).toMatchObject({
            selectedProvider: "arkos",
            selectedProviderInstanceId: "codex_work",
            selectedModel: "gpt-5.4",
            selectedProviderModelOptions: { reasoningEffort: "high" },
        });
        flushSync(() => hook.result.current.handleProviderModelChange("arkos", "gpt-5.4-mini", "codex_personal"));
        expect(hook.result.current).toMatchObject({
            selectedProvider: "arkos",
            selectedProviderInstanceId: "codex_personal",
            selectedModel: "gpt-5.4-mini",
        });
        expect(useComposerDraftStore.getState().stickyModelSelectionByProvider.codex_work?.model).toBe("gpt-5.4");
        expect(useComposerDraftStore.getState().stickyModelSelectionByProvider.codex_personal?.model).toBe("gpt-5.4-mini");
    }
    finally {
        await hook.unmount();
    }
});
