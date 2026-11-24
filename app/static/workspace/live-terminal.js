"use strict";

(() => {
  const tr = window.logsenseTranslate;
  const local = window.localWorkbench;
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const requestTimeout = 5000;

  function canRetry(error) {
    return error instanceof TypeError || error instanceof SyntaxError || error.name === "AbortError" ||
      error.status === 408 || error.status === 429 || error.status >= 500;
  }

  class LiveTerminal {
    constructor(host, profile, reportError) {
      this.host = host;
      const { workspace = "project", ...shell } = profile;
      this.profile = shell;
      this.service = local.scope(workspace);
      this.root = profile.shell === "SSH" ? null : workspace === "code" ? state.codeRoot : state.localRoot;
      this.reportError = reportError;
      this.session = null;
      this.closed = false;
      this.generation = 0;
      this.inputEpoch = 0;
      this.input = Promise.resolve();
      this.pendingInput = "";
    }

    async begin() {
      try {
        if (!this.service.authorized) throw new Error(tr("Open the workbench from the launcher."));
        if (!window.Terminal || !window.FitAddon) throw new Error(tr("Missing xterm.js assets."));
        const { id, cwd, interpreter } = await this.service.call("/terminals", "POST", this.profile);
        if (this.closed) await this.service.call("/terminals/" + id, "DELETE", undefined, true);
        else {
          this.session = id;
          if (cwd) this.host.title = tr("Folder when the session opened: {0}", cwd) + (interpreter ? "\nPython: " + interpreter : "");
          this.attach();
        }
      } catch (error) {
        this.reportError(error.message);
        this.host.textContent = error.message;
      }
    }

    attach() {
      if (this.closed || !this.session) return;
      this.disposeView();
      const generation = ++this.generation;
      const emulator = new Terminal({
        cursorBlink: true, fontFamily: 'Consolas, "SFMono-Regular", monospace', fontSize: 13,
        scrollback: 2000, allowProposedApi: false, disableStdin: true,
        theme: this.theme()
      });
      this.emulator = emulator;
      const owner = this.host.ownerDocument;
      const status = owner.createElement("div");
      status.className = "terminal-connection";
      status.setAttribute("role", "status");
      status.textContent = tr("Connecting to session…");
      const viewport = owner.createElement("div");
      viewport.className = "live-shell-viewport";
      this.host.replaceChildren(status, viewport);
      emulator.open(viewport);
      if (this.root) {
        const links = window.WorkbenchSourceLinks;
        emulator.registerLinkProvider({
          provideLinks: (line, callback) => {
            const buffer = emulator.buffer.active;
            let start = line - 1;
            let end = start;
            while (start > 0 && line - start < 8 && buffer.getLine(start)?.isWrapped) start -= 1;
            while (end - start < 7 && buffer.getLine(end + 1)?.isWrapped) end += 1;
            if (buffer.getLine(start)?.isWrapped || buffer.getLine(end + 1)?.isWrapped) return callback();
            let text = "";
            for (let index = start; index <= end; index += 1) text += buffer.getLine(index)?.translateToString(index === end) || "";
            const target = text && links.reference(text, this.root);
            // A shell may have changed working directory, so only use absolute paths here.
            callback(target?.absolute ? [{
              range: { start: { x: 1, y: start + 1 }, end: { x: emulator.cols, y: end + 1 } },
              text,
              activate: () => links.open(target)
            }] : undefined);
          }
        });
      }
      const fit = new FitAddon.FitAddon();
      emulator.loadAddon(fit);
      let sentSize = "";
      const resize = () => {
        if (!this.current(generation) || !viewport.clientWidth || !viewport.clientHeight) return;
        fit.fit();
        if (emulator.options.disableStdin) return;
        const rows = Math.max(2, Math.min(180, emulator.rows));
        const columns = Math.max(2, Math.min(400, emulator.cols));
        const size = rows + ":" + columns;
        if (size === sentSize) return;
        sentSize = size;
        this.service.call("/terminals/" + this.session, "POST", { rows, columns }).catch((error) => {
          if (sentSize === size) sentSize = "";
          if (this.current(generation)) this.reportError(error.message);
        });
      };
      this.observer = new ResizeObserver(resize);
      this.observer.observe(viewport);
      emulator.onData((data) => {
        this.pendingInput += data;
        if (this.pendingInput.length >= 8192 || /[\r\n\x03]/.test(data)) this.flushInput(generation);
        else this.inputTimer ??= setTimeout(() => this.flushInput(generation), 12);
      });
      this.poll(generation, emulator, status, resize);
    }

    current(generation) {
      return !this.closed && generation === this.generation;
    }

    theme() {
      const style = this.host.ownerDocument.defaultView.getComputedStyle(this.host);
      const foreground = style.getPropertyValue("--terminal-text").trim();
      return { background: style.getPropertyValue("--terminal-bg").trim(), foreground, cursor: foreground };
    }

    refreshTheme() {
      if (this.emulator) this.emulator.options.theme = this.theme();
    }

    discardPendingInput() {
      clearTimeout(this.inputTimer);
      this.inputTimer = null;
      this.pendingInput = "";
    }

    flushInput(generation) {
      const data = this.pendingInput;
      this.discardPendingInput();
      const epoch = this.inputEpoch;
      for (let start = 0, end; start < data.length; start = end) {
        end = Math.min(start + 8192, data.length);
        // Never split a Unicode surrogate pair between two PTY writes.
        if (end < data.length && /[\uD800-\uDBFF]/.test(data[end - 1])) end -= 1;
        const chunk = data.slice(start, end);
        this.input = this.input.then(() => this.sendInput(chunk, generation, epoch));
      }
    }

    async sendInput(text, generation, epoch) {
      if (!this.current(generation) || epoch !== this.inputEpoch || this.emulator.options.disableStdin) return;
      const controller = new AbortController();
      this.inputRequest = controller;
      const timeout = setTimeout(() => controller.abort(), requestTimeout);
      try {
        await this.service.call("/terminals/" + this.session, "POST", { text }, false, controller.signal);
      } catch (error) {
        if (this.current(generation) && epoch === this.inputEpoch) {
          this.inputEpoch += 1;
          this.discardPendingInput();
          this.reportError(error.status ? error.message : tr("Could not confirm the command reached the shell. Check the output before sending it again."));
        }
      } finally {
        clearTimeout(timeout);
        this.inputRequest = null;
      }
    }

    async readOutput(offset) {
      const controller = new AbortController();
      this.outputRequest = controller;
      const timeout = setTimeout(() => controller.abort(), requestTimeout);
      try {
        const path = this.service.query("/terminals/" + this.session, { offset, wait_ms: 500 });
        return await this.service.call(path, "GET", undefined, false, controller.signal);
      } finally {
        clearTimeout(timeout);
        if (this.outputRequest === controller) this.outputRequest = null;
      }
    }

    async poll(generation, emulator, status, resize) {
      let offset = 0;
      let retryDelay = 250;
      let interrupted = false;
      while (this.current(generation)) {
        try {
          const output = await this.readOutput(offset);
          if (!this.current(generation)) return;
          if (output.reset) {
            const skipped = output.start_offset - offset;
            const message = skipped > 0 ? tr("{0} output characters exceeded the buffer.", skipped) : tr("The read position changed.");
            emulator.write("\r\n[" + message + "]\r\n");
          }
          if (output.text) emulator.write(output.text);
          offset = output.offset;
          if (output.finished) {
            emulator.options.disableStdin = true;
            status.textContent = tr("Session ended.");
            emulator.write("\r\n[" + tr("Session ended") + "]\r\n");
            return;
          }
          if (emulator.options.disableStdin) {
            emulator.options.disableStdin = false;
            status.textContent = interrupted ? tr("Reconnected to the same session.") : "";
            resize();
            const pane = this.host.closest(".terminal-pane");
            if (!interrupted && !pane?.dataset.tool && pane?.contains(this.host.ownerDocument.activeElement)) emulator.focus();
          }
          interrupted = false;
          retryDelay = 250;
          if (output.text) await delay(16);
        } catch (error) {
          if (!this.current(generation)) return;
          emulator.options.disableStdin = true;
          if (!interrupted) {
            this.inputEpoch += 1;
            this.discardPendingInput();
            this.inputRequest?.abort();
          }
          if (!canRetry(error)) {
            status.textContent = error.status === 404 ? tr("The shell session no longer exists on the server.") : error.message;
            return;
          }
          interrupted = true;
          status.textContent = tr("Connection lost. Trying to reconnect to the session…");
          await delay(retryDelay);
          retryDelay = Math.min(retryDelay * 2, 4000);
        }
      }
    }

    disposeView() {
      this.discardPendingInput();
      this.outputRequest?.abort();
      this.inputRequest?.abort();
      this.observer?.disconnect();
      this.emulator?.dispose();
    }

    close() {
      this.closed = true;
      this.disposeView();
      if (this.session) this.service.call("/terminals/" + this.session, "DELETE", undefined, true).catch(() => {});
    }
  }
  window.WorkbenchTerminal = LiveTerminal;
})();
