// Small, local startup markers for the desktop performance probe. StrictMode
// and HMR must not turn these into a stream of repeated measurements.
export function markRendererStartup(stage: string): void {
  const name = `arkos-startup:${stage}`;
  if (performance.getEntriesByName(name).length === 0) performance.mark(name);
}
