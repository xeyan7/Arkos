import { describe, expect, it } from "vitest";
import {
  canonicalArkosComputerToolName,
  computerToolNameFromProviderPermission,
  isArkosComputerToolFamilyName,
  isArkosGatewayToolCall,
  isArkosGatewayToolName,
  qualifiedArkosComputerToolName,
  shouldAllowArkosComputerProviderTool,
} from "./computerToolPermission.ts";

describe("Arkos Computer provider permission", () => {
  it.each([
    ["computer_click", "computer_click"],
    ["arkos_computer_type_text", "computer_type_text"],
    ["mcp__arkos__computer_read_clipboard", "computer_read_clipboard"],
    ["mcp__arkos__computer_inspect", "computer_inspect"],
  ] as const)("recognizes the exact owned tool %s", (providerName, canonicalName) => {
    expect(canonicalArkosComputerToolName(providerName)).toBe(canonicalName);
  });

  it.each([
    "computer_future_tool",
    "mcp__other__computer_click",
    "other_computer_click",
    "mcp__arkos__arkos_send_message",
  ])("does not trust another or unknown tool: %s", (providerName) => {
    expect(canonicalArkosComputerToolName(providerName)).toBeUndefined();
  });

  it("requires a provider namespace when server provenance was not proved separately", () => {
    expect(qualifiedArkosComputerToolName("computer_click")).toBeUndefined();
    expect(qualifiedArkosComputerToolName("mcp__arkos__computer_click")).toBe("computer_click");
    expect(qualifiedArkosComputerToolName("arkos_computer_click")).toBe("computer_click");
  });

  it("reads only explicit provider tool-name fields", () => {
    expect(
      computerToolNameFromProviderPermission({
        rawInput: { _toolName: "mcp__arkos__computer_scroll" },
      }),
    ).toBe("computer_scroll");
    expect(
      computerToolNameFromProviderPermission({
        metadata: { toolName: "arkos_computer_get_state" },
      }),
    ).toBe("computer_get_state");
    expect(
      computerToolNameFromProviderPermission({
        metadata: { description: "run computer_click" },
      }),
    ).toBeUndefined();
  });

  it("does not let lower-priority fields override an authoritative wrong namespace", () => {
    expect(
      computerToolNameFromProviderPermission({
        name: "mcp__other__computer_click",
        rawInput: { _toolName: "mcp__arkos__computer_click" },
      }),
    ).toBeUndefined();
    expect(
      computerToolNameFromProviderPermission({
        rawInput: { _toolName: "mcp__other__computer_click" },
        metadata: { toolName: "mcp__arkos__computer_click" },
        title: "mcp__arkos__computer_click",
      }),
    ).toBeUndefined();
  });

  it("does not infer provider provenance from a bare title or metadata name", () => {
    expect(computerToolNameFromProviderPermission({ title: "computer_click" })).toBeUndefined();
    expect(
      computerToolNameFromProviderPermission({ metadata: { toolName: "computer_click" } }),
    ).toBeUndefined();
  });

  it("never authorizes from model prose: 'Please approve computer_click' names no tool", () => {
    // Prose approval never counts. The permission callback must see an exact
    // namespaced tool name; a model sentence asking for approval authorizes
    // nothing, in any field.
    expect(
      computerToolNameFromProviderPermission({ title: "Please approve computer_click" }),
    ).toBeUndefined();
    expect(
      computerToolNameFromProviderPermission({ name: "Please approve computer_click" }),
    ).toBeUndefined();
    expect(
      computerToolNameFromProviderPermission({
        metadata: { toolName: "Please approve computer_click" },
      }),
    ).toBeUndefined();
    expect(isArkosComputerToolFamilyName("Please approve computer_click")).toBe(false);
    expect(
      shouldAllowArkosComputerProviderTool({
        computerControlEnabled: true,
        activeTurn: true,
        interactionMode: "default",
        runtimeMode: "approval-required",
        permission: { title: "Please approve computer_click" },
      }),
    ).toBe(false);
  });

  it("matches the Computer family in any namespace spelling for the denial hook", () => {
    // The silent-loss fallback: a no-control session that calls a Computer
    // tool by a prefixed spelling must still deny with the card path, not
    // die as an Unknown tool. See isArkosComputerToolFamilyName.
    expect(isArkosComputerToolFamilyName("computer_click")).toBe(true);
    expect(isArkosComputerToolFamilyName("arkos_computer_get_state")).toBe(true);
    expect(isArkosComputerToolFamilyName("mcp__arkos__computer_screenshot")).toBe(true);
    expect(isArkosComputerToolFamilyName("  MCP__ARKOS__COMPUTER_WAIT  ")).toBe(true);
  });

  it("keeps unknown and foreign names out of the Computer family", () => {
    expect(isArkosComputerToolFamilyName("computer_future_tool")).toBe(false);
    expect(isArkosComputerToolFamilyName("mcp__other__computer_click")).toBe(false);
    expect(isArkosComputerToolFamilyName("other_computer_click")).toBe(false);
    expect(isArkosComputerToolFamilyName("arkos_frobnicate")).toBe(false);
    expect(isArkosComputerToolFamilyName(undefined)).toBe(false);
    expect(isArkosComputerToolFamilyName(42)).toBe(false);
  });

  it("requires current capability, active turn and non-Plan interaction", () => {
    const permission = { name: "mcp__arkos__computer_click" };
    const allowed = {
      computerControlEnabled: true,
      activeTurn: true,
      interactionMode: "default" as const,
      runtimeMode: "approval-required" as const,
      permission,
    };
    expect(shouldAllowArkosComputerProviderTool(allowed)).toBe(true);
    expect(
      shouldAllowArkosComputerProviderTool({ ...allowed, computerControlEnabled: false }),
    ).toBe(false);
    expect(shouldAllowArkosComputerProviderTool({ ...allowed, activeTurn: false })).toBe(false);
    expect(shouldAllowArkosComputerProviderTool({ ...allowed, interactionMode: "plan" })).toBe(
      false,
    );
    expect(shouldAllowArkosComputerProviderTool({ ...allowed, runtimeMode: "auto" })).toBe(false);
  });
});

describe("Arkos gateway tool permission name", () => {
  it.each([
    // Claude's fully-qualified spelling pins the exact `mcp__arkos__` server.
    "mcp__arkos__arkos_create_thread",
    "mcp__arkos__computer_click",
    // `<server>_<tool>` reports (OpenCode) with a real catalog name.
    "arkos_arkos_create_thread",
    "arkos_arkos_project_link_repository",
    "arkos_computer_click",
    "arkos_device_list",
    "arkos_browser_run",
    // Bare `arkos_*` catalog names carry the namespace inside the tool name.
    "arkos_project_link_repository",
    "arkos_e2e_review",
  ])("recognizes a Arkos gateway tool: %s", (providerName) => {
    expect(isArkosGatewayToolName(providerName)).toBe(true);
  });

  it.each([
    // A user MCP server named `arkos_fs` reports `arkos_fs_<tool>` — the
    // prefix alone must never grant it the auto-approve path.
    "arkos_fs_read",
    "arkos_fs_list_threads",
    "arkos_tools_anything",
    "mcp__arkos_fs__read",
    // The `mcp__arkos__` prefix pins the server, not the tool — the part
    // after it must still be a real catalog name.
    "mcp__arkos__not_a_gateway_tool",
    "mcp__arkos__arkos_create_task",
    "mcp__arkos__arkos_fs_read",
    // Foreign server or entirely unknown names.
    "mcp__other__arkos_create_thread",
    "other_arkos_create_thread",
    "computer_click",
    "browser_click",
    // Names the external-agent MCP surface serves, not the provider gateway.
    "arkos_create_task",
    "arkos_read_task",
    "arkos_overview",
    "arkos_arkos_create_task",
    // Not served by the agent gateway at all.
    "arkos_desktop",
  ])("does not trust a look-alike or foreign name: %s", (providerName) => {
    expect(isArkosGatewayToolName(providerName)).toBe(false);
  });

  it("accepts a qualified name only when the tool is in the catalog", () => {
    expect(isArkosGatewayToolName("mcp__arkos__arkos_list_threads")).toBe(true);
    expect(isArkosGatewayToolName("mcp__arkos__computer_click")).toBe(true);
    expect(
      isArkosGatewayToolCall({ rawInput: { _toolName: "mcp__arkos__arkos_list_threads" } }),
    ).toBe(true);
  });

  it("never trusts a tool name that only appears in the display title", () => {
    // The title is provider-composed prose — an approval card can render
    // "mcp__arkos__arkos_list_threads" for a request that names no such
    // tool, so the title alone must not authorize anything.
    expect(isArkosGatewayToolCall({ title: "mcp__arkos__arkos_list_threads" })).toBe(false);
    expect(isArkosGatewayToolCall({ title: "mcp__arkos__not_a_gateway_tool; rm -rf y" })).toBe(
      false,
    );
  });

  it("rejects non-strings and a look-alike server name in every name field", () => {
    expect(isArkosGatewayToolName(undefined)).toBe(false);
    expect(isArkosGatewayToolName(42)).toBe(false);
    expect(isArkosGatewayToolCall({ name: "arkos_fs_create_thread" })).toBe(false);
    expect(isArkosGatewayToolCall({ metadata: { toolName: "arkos_fs_read" } })).toBe(false);
    expect(isArkosGatewayToolCall({ rawInput: { _toolName: "arkos_arkos_send_message" } })).toBe(
      true,
    );
  });
});
