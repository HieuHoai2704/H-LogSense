"use strict";

// Quit prompt for the desktop window. Closing the window asks the page first (window.hlogsenRequestQuit,
// called by the desktop host); the page answers with its own dialog and closes the window through the
// authenticated desktop bridge. With unsaved code edits it offers Save and quit / Quit without saving.
(() => {
  const tr = (message, ...values) =>
    window.logsenseTranslate ? window.logsenseTranslate(message, ...values) : message.replace(/\{(\d+)\}/g, (_, i) => values[i]);
  const trn = (count, one, other, ...values) =>
    window.logsenseTranslatePlural ? window.logsenseTranslatePlural(count, one, other, ...values)
      : (count === 1 ? one : other).replace(/\{(\d+)\}/g, (_, i) => values[i]);
  let open = null;

  function token() {
    try { return sessionStorage.getItem("h-logsen-workbench"); } catch { return null; }
  }

  function quit() {
    const api = window.pywebview?.api;
    if (api?.quit) api.quit(token());
  }

  function style() {
    if (document.getElementById("quit-dialog-style")) return;
    const css = document.createElement("style");
    css.id = "quit-dialog-style";
    css.textContent = `
      .quit-dialog { padding: 0; border: 1px solid #3b3b3b; border-radius: 12px; color: #ededeb; background: #161617;
        box-shadow: 0 18px 60px rgb(0 0 0 / .55); width: min(440px, calc(100vw - 32px));
        font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif; }
      .quit-dialog::backdrop { background: rgb(0 0 0 / .62); }
      .quit-dialog form { display: grid; gap: 14px; padding: 22px 22px 18px; margin: 0; }
      .quit-dialog h2 { margin: 0; font-size: 17px; }
      .quit-dialog p { margin: 0; color: #b4b4b0; }
      .quit-dialog .quit-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 4px; }
      .quit-dialog button { min-height: 34px; padding: 0 14px; border-radius: 8px; border: 1px solid #4a4a4a;
        color: #ededeb; background: transparent; font: inherit; font-weight: 600; cursor: pointer; }
      .quit-dialog button:hover { background: rgb(255 255 255 / .08); }
      .quit-dialog button.primary { color: #0b0b0c; background: #f4f4f2; border-color: #f4f4f2; }
      .quit-dialog button.primary:hover { background: #ffffff; }
      .quit-dialog button.danger { color: #ff8a80; border-color: #7a3833; }
      .quit-dialog button:focus-visible { outline: 2px solid #f4f4f2; outline-offset: 2px; }`;
    document.head.append(css);
  }

  function button(label, kind, action) {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    if (kind) element.className = kind;
    element.addEventListener("click", action);
    return element;
  }

  window.hlogsenRequestQuit = () => {
    if (open) {
      open.querySelector("button")?.focus();
      return true;
    }
    style();
    const editor = window.hlogsenEditor;
    const unsaved = editor?.unsaved?.() || 0;
    const dialog = document.createElement("dialog");
    dialog.className = "quit-dialog";
    dialog.setAttribute("aria-labelledby", "quit-dialog-title");
    const form = document.createElement("form");
    form.method = "dialog";
    const title = document.createElement("h2");
    title.id = "quit-dialog-title";
    const text = document.createElement("p");
    const actions = document.createElement("div");
    actions.className = "quit-actions";
    const close = () => { dialog.close(); dialog.remove(); open = null; };
    const cancel = button(tr("Cancel"), "", close);
    if (unsaved) {
      title.textContent = tr("Save changes before quitting?");
      text.textContent = trn(unsaved, "{0} open file has unsaved changes.", "{0} open files have unsaved changes.", unsaved);
      const save = button(tr("Save and quit"), "primary", async () => {
        save.disabled = true;
        save.textContent = tr("Saving…");
        if (await editor.saveAll()) quit();
        else {
          save.disabled = false;
          save.textContent = tr("Save and quit");
          text.textContent = tr("Some files could not be saved. Check the status bar, then try again.");
        }
      });
      actions.append(cancel, button(tr("Quit without saving"), "danger", quit), save);
    } else {
      title.textContent = tr("Quit H-logsen?");
      text.textContent = tr("You will be signed out. Sign in again the next time you open the app.");
      actions.append(cancel, button(tr("Quit"), "primary", quit));
    }
    form.append(title, text, actions);
    dialog.append(form);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
    document.body.append(dialog);
    open = dialog;
    dialog.showModal();
    actions.lastElementChild.focus();
    return true;
  };
})();
