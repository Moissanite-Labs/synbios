import React, { Suspense } from "react";
import { createRoot } from "react-dom/client";

// Loading the inspection console is explicit so its stylesheet cannot change the
// designer's Crystal Lattice composition.
const App = new URLSearchParams(window.location.search).has("advanced")
  ? React.lazy(() => import("./LegacyForge"))
  : React.lazy(() => import("./mission/MissionControl"));
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Suspense fallback={<p>Opening Synbios…</p>}>
      <App />
    </Suspense>
  </React.StrictMode>,
);
