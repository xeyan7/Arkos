// FILE: bootstrap.ts
// Purpose: Completes synchronous renderer storage migration before any app store can hydrate.

import "./storageOriginMigration";

import { bootstrapSignedOutScreen } from "./authSignedOut";
import { bootstrapPairingSession } from "./pairingBootstrap";
import { markRendererStartup } from "./rendererStartupTiming";

markRendererStartup("bootstrap");

if (!bootstrapSignedOutScreen()) {
  void bootstrapPairingSession().then((result) => {
    if (result === "not-pairing") {
      markRendererStartup("main-import-start");
      return import("./main").then(() => markRendererStartup("main-import-complete"));
    }
  });
}
