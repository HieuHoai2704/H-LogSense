"use strict";

// Sign-in page: keep the launcher's workbench token. The server redirected here before the workspace
// page could read it from the launch URL.
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

// Staff sign-in, sign-up and administrator sign-in share one card. Switching changes its data-mode:
// the panel sweeps, the forms slide out and in, and the URL and title follow without a reload.
(() => {
  const card = document.querySelector("[data-auth-card]");
  if (!card) return;
  const modes = ["staff", "signup", "admin"];
  const forms = Object.fromEntries(modes.map((mode) => [mode, card.querySelector(".form-box.pane-" + mode)]));
  const infos = Object.fromEntries(modes.map((mode) => [mode, card.querySelector(".info-content.pane-" + mode)]));
  const url = Object.fromEntries(modes.map((mode) => [mode, forms[mode].querySelector("form").getAttribute("action")]));
  const tabs = document.querySelectorAll(".auth-tabs [data-auth-switch]");
  // The entrance animation is decoration: if a window does not paint frames, the form still appears.
  setTimeout(() => card.classList.remove("intro"), 2000);

  function show(mode, push) {
    if (!modes.includes(mode) || card.dataset.mode === mode) return;
    card.classList.remove("intro");
    card.dataset.mode = mode;
    for (const name of modes) {
      forms[name].inert = name !== mode;
      infos[name].setAttribute("aria-hidden", String(name !== mode));
    }
    const tab = mode === "admin" ? "admin" : "staff";
    for (const link of tabs) {
      if (link.dataset.authSwitch === tab) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    document.title = card.dataset[mode + "Title"];
    if (push) history.pushState({ mode }, "", url[mode] + (mode === "signup" ? "" : location.search));
    const target = forms[mode].querySelector("input:not([type=hidden])");
    setTimeout(() => target?.focus({ preventScroll: true }), 850);
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-auth-switch]");
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    show(link.dataset.authSwitch, true);
  });
  window.addEventListener("popstate", () => {
    show(modes.find((mode) => url[mode] === location.pathname) || "staff", false);
  });
})();

// Show / hide password. The field returns to hidden when its form is submitted.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-reveal]");
  if (!button) return;
  const input = document.getElementById(button.getAttribute("aria-controls"));
  if (!input) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  input.toggleAttribute("data-revealed", show);
  button.setAttribute("aria-pressed", String(show));
  button.setAttribute("aria-label", button.dataset[show ? "hideLabel" : "showLabel"]);
  input.focus({ preventScroll: true });
});
document.addEventListener("submit", (event) => {
  for (const input of event.target.querySelectorAll("input[data-revealed]")) {
    input.type = "password";
    input.removeAttribute("data-revealed");
  }
});
