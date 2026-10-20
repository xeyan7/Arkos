export function resolveDesktopRendererMode(input: {
  readonly isPackaged: boolean;
  readonly isSourceDesktopBuild: boolean;
  readonly devServerUrl: string | undefined;
  readonly bundledRenderer: string | undefined;
}) {
  const supportsDevelopment = !input.isPackaged || input.isSourceDesktopBuild;
  const useBundledRenderer = supportsDevelopment && /^(1|true)$/i.test(input.bundledRenderer?.trim() ?? "");
  return {
    isDevelopment: supportsDevelopment && (Boolean(input.devServerUrl) || useBundledRenderer),
    useBundledRenderer,
  };
}
