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

// Staff / administrator switch without a reload: the panel sweeps across and the forms slide over.
(() => {
  const card = document.querySelector("[data-auth-card]");
  if (!card) return;
  const staff = card.querySelector(".form-box.staff");
  const admin = card.querySelector(".form-box.admin");
  const tabs = document.querySelectorAll(".auth-tabs [data-auth-switch]");
  const url = { staff: staff.querySelector("form").getAttribute("action"), admin: admin.querySelector("form").getAttribute("action") };
  // The entrance animation is decoration: if a window does not paint frames, the form still appears.
  setTimeout(() => card.classList.remove("intro"), 2000);

  function show(portal, push) {
    const toAdmin = portal === "admin";
    if (card.classList.contains("admin") === toAdmin) return;
    card.classList.remove("intro");
    card.classList.toggle("admin", toAdmin);
    staff.inert = toAdmin;
    admin.inert = !toAdmin;
    card.querySelector(".info-content.staff").setAttribute("aria-hidden", String(toAdmin));
    card.querySelector(".info-content.admin").setAttribute("aria-hidden", String(!toAdmin));
    for (const tab of tabs) {
      if (tab.dataset.authSwitch === portal) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    }
    document.title = card.dataset[toAdmin ? "adminTitle" : "staffTitle"];
    if (push) history.pushState({ portal }, "", url[portal] + location.search);
    const target = (toAdmin ? admin : staff).querySelector("input:not([type=hidden])");
    setTimeout(() => target?.focus({ preventScroll: true }), 900);
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-auth-switch]");
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    show(link.dataset.authSwitch, true);
  });
  window.addEventListener("popstate", () => show(location.pathname === url.admin ? "admin" : "staff", false));
})();
