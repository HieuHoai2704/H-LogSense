"use strict";

// Sign-in page: keep the desktop launcher's workbench token. The server redirected here before the
// workspace page could read it from the launch URL.
(() => {
  const params = new URLSearchParams(location.hash.slice(1));
  const supplied = params.get("workbench");
  if (supplied) {
    try {
      sessionStorage.setItem("h-logsen-workbench", supplied);
    } catch {
      // Without storage the workspace asks to be reopened from the launcher.
    }
    history.replaceState(history.state, "", location.pathname + location.search);
  }

})();
