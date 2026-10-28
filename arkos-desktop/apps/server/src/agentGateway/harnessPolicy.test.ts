import { assert, describe, it } from "@effect/vitest";
import { AUTOMATION_AUTHORING_GUIDANCE } from "./automationAuthoringGuidance.ts";
import { renderArkosHarnessPolicy, ARKOS_HARNESS_POLICY_MARKER, takeArkosHarnessPolicyForProviderSession, takeArkosHarnessPolicyTextPartForProviderSession, takeArkosHarnessPolicyForSession, } from "./harnessPolicy.ts";
describe("Arkos harness policy", () => {
    it("defers duplicate automation authoring text while preserving tool routing and run rules", () => {
        const inline = renderArkosHarnessPolicy({ gatewayControlAvailable: true });
        const deferred = renderArkosHarnessPolicy({
            gatewayControlAvailable: true,
            automationAuthoring: "tool-descriptions",
        });
        assert.equal(deferred, inline.replace(`${AUTOMATION_AUTHORING_GUIDANCE}\n`, ""));
        assert.include(deferred, "arkos_create_automation");
        assert.include(deferred, "arkos_view_automation");
        assert.include(deferred, "arkos_report_automation_result");
    });
    it("includes honest completion evidence and opt-in delegated E2E testing", () => {
        const policy = renderArkosHarnessPolicy({ gatewayControlAvailable: true });
        for (const text of [
            "completion report",
            "artifactPath",
            "![Result description]",
            "explicitly asked",
            "arkos_e2e_review",
            "Do not load it for unrelated work",
        ]) {
            assert.include(policy, text);
        }
        assert.notInclude(renderArkosHarnessPolicy({ gatewayControlAvailable: false }), "browser_screenshot({kind:'proof'})");
    });
    it("identifies Arkos and explains exact batch coordination when MCP is available", () => {
        const policy = renderArkosHarnessPolicy({ gatewayControlAvailable: true });
        assert.include(policy, ARKOS_HARNESS_POLICY_MARKER);
        assert.include(policy, "Arkos is the host and harness");
        assert.include(policy, "one exact arkos_create_threads plan");
        assert.include(policy, "before returning an operationId");
        assert.include(policy, "arkos_wait_for_threads");
        assert.include(policy, "arkos_set_thread_pull_request");
        assert.include(policy, "current thread's own deliverable");
        assert.include(policy, "only reviews, references, or discusses");
        assert.include(policy, "use browser_* autonomously");
        assert.include(policy, "canonical, complete control surface");
        assert.include(policy, "never substitute Chrome");
        assert.include(policy, "user's active chat");
        assert.include(policy, "Detailed rules live in each tool description");
        assert.notInclude(policy, "BrowserInterruptedByHuman");
        assert.notInclude(policy, "start with browser_open");
        assert.include(policy, "do not create Arkos threads");
        assert.include(policy, "specific 3–8 word outcome label");
        assert.include(policy, "Assume no chat context");
        assert.include(policy, "notify-versus-silent criteria");
        assert.include(policy, 'later manual follow-up such as "continue"');
        assert.include(policy, "Never call this tool for a manual follow-up turn");
    });
    it("asks agents to emit known absolute file URLs instead of invented relative links", () => {
        const gateway = renderArkosHarnessPolicy({ gatewayControlAvailable: true });
        const identityOnly = renderArkosHarnessPolicy({ gatewayControlAvailable: false });
        for (const policy of [gateway, identityOnly]) {
            assert.include(policy, "[config.ts](file:///absolute/path/config.ts)");
            assert.include(policy, "Relative links are only for the session working directory");
            assert.include(policy, "use plain text and never invent a path");
        }
    });
    it("keeps final answers self-contained when intermediate progress is collapsed", () => {
        const gateway = renderArkosHarnessPolicy({ gatewayControlAvailable: true });
        const identityOnly = renderArkosHarnessPolicy({ gatewayControlAvailable: false });
        for (const policy of [gateway, identityOnly]) {
            assert.include(policy, 'under "Worked for..."');
            assert.include(policy, "Final responses must restate every needed scope");
            assert.include(policy, 'Never request approval using "this", "the above"');
            assert.include(policy, "structured user-input tool");
            assert.include(policy, "include all decision context");
        }
    });
    it("never advertises gateway mutation to providers without scoped MCP", () => {
        const policy = renderArkosHarnessPolicy({ gatewayControlAvailable: false });
        assert.include(policy, "Arkos MCP control is unavailable");
        assert.notInclude(policy, "one exact arkos_create_threads plan");
    });
    it("delivers a private host-context block once per provider session", () => {
        const state: {
            harnessPolicyDelivered?: boolean;
        } = {};
        assert.include(takeArkosHarnessPolicyForSession(state, { gatewayControlAvailable: true }) ?? "", "<arkos_host_context>");
        assert.isNull(takeArkosHarnessPolicyForSession(state, { gatewayControlAvailable: true }));
        // The text-part form ACP adapters inject obeys the same once-per-session latch.
        const partState: {
            harnessPolicyDelivered?: boolean;
        } = {};
        const input = { provider: "arkos", scopedGatewayConnectionAvailable: true } as const;
        assert.include(takeArkosHarnessPolicyTextPartForProviderSession(partState, input)?.text ?? "", ARKOS_HARNESS_POLICY_MARKER);
        assert.isNull(takeArkosHarnessPolicyTextPartForProviderSession(partState, input));
    });
    it("keeps OpenCode and Pi identity-only until scoped setup succeeds", () => {
        for (const provider of ["arkos", "arkos"] as const) {
            const text = takeArkosHarnessPolicyForProviderSession({}, { provider, scopedGatewayConnectionAvailable: false }) ?? "";
            assert.include(text, ARKOS_HARNESS_POLICY_MARKER, provider);
            assert.include(text, "Arkos MCP control is unavailable", provider);
            assert.notInclude(text, "one exact arkos_create_threads plan", provider);
        }
    });
    it("routes iOS work to device tools without embedding per-tool instructions", () => {
        const policy = renderArkosHarnessPolicy({ gatewayControlAvailable: true });
        assert.include(policy, "any-language iOS app or simulator request");
        assert.include(policy, "call device_* directly and autonomously");
        assert.include(policy, "never use xcrun simctl");
        assert.include(policy, "open Simulator.app");
        assert.include(policy, "user watches the streamed pane");
        assert.notInclude(policy, "device_list first");
        assert.notInclude(policy, "com.apple.Preferences");
    });
    it("keeps the gateway policy below its prompt budget", () => {
        assert.isAtMost(renderArkosHarnessPolicy({ gatewayControlAvailable: true }).length, 6030);
    });
    it("withholds device guidance from sessions with no gateway control", () => {
        const policy = renderArkosHarnessPolicy({ gatewayControlAvailable: false });
        // Promising tools this session cannot reach would be a lie.
        assert.notInclude(policy, "device_list");
        assert.notInclude(policy, "device_describe_ui");
    });
    it("includes Computer tool guidance only when the session can use Computer", () => {
        for (const gatewayControlAvailable of [true, false] as const) {
            for (const enableComputerControl of [true, false, undefined] as const) {
                const policy = renderArkosHarnessPolicy({
                    gatewayControlAvailable,
                    ...(enableComputerControl === undefined ? {} : { enableComputerControl }),
                });
                const scope = `${gatewayControlAvailable}/${enableComputerControl}`;
                if (gatewayControlAvailable && enableComputerControl === true) {
                    assert.include(policy, "## Arkos computer use", scope);
                    assert.include(policy, "The computer_* tools are live on this session", scope);
                }
                else {
                    assert.notInclude(policy, "## Arkos computer use", scope);
                    assert.notInclude(policy, "computer_", scope);
                    assert.notInclude(policy, "turn Computer control on in Settings", scope);
                }
            }
        }
    });
});
it("adds Computer guidance only for an explicitly enabled scoped session across all providers", () => {
    const providers = [
        "arkos",
        "arkos",
        "arkos",
        "arkos",
        "arkos",
        "arkos",
        "arkos",
        "arkos",
        "arkos",
    ] as const;
    for (const provider of providers) {
        const off = takeArkosHarnessPolicyForProviderSession({}, { provider, scopedGatewayConnectionAvailable: true });
        const explicitOff = takeArkosHarnessPolicyForProviderSession({ enableComputerControl: false }, { provider, scopedGatewayConnectionAvailable: true });
        assert.strictEqual(off, explicitOff);
        assert.notInclude(off ?? "", "## Arkos computer use");
        assert.notInclude(off ?? "", "computer_", provider);
        const state = { enableComputerControl: true };
        const on = takeArkosHarnessPolicyForProviderSession(state, {
            provider,
            scopedGatewayConnectionAvailable: true,
        }) ?? "";
        assert.equal(on.split("## Arkos computer use").length - 1, 1, provider);
        assert.include(on, "never replay it");
        assert.isNull(takeArkosHarnessPolicyForProviderSession(state, {
            provider,
            scopedGatewayConnectionAvailable: true,
        }));
        assert.notInclude(takeArkosHarnessPolicyForProviderSession({ enableComputerControl: true }, { provider, scopedGatewayConnectionAvailable: false }) ?? "", "## Arkos computer use");
    }
});
