"""Tkinter desktop companion for the authenticated H-logsen workspace."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

from config import APP_NAME
from scripts.logsense_client import ApiError, LogSenseClient, write_log_csv


class Tooltip:
    def __init__(self, widget, text):
        self.tip = None
        widget.bind("<Enter>", lambda event: self.show(widget, text))
        widget.bind("<Leave>", lambda event: self.hide())

    def show(self, widget, text):
        self.hide()
        self.tip = tk.Toplevel(widget)
        self.tip.overrideredirect(True)
        self.tip.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height()}")
        ttk.Label(self.tip, text=text, padding=6, relief="raised").grid()

    def hide(self):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class Desktop:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} · Desktop")
        self.root.minsize(760, 570)
        assets = Path(__file__).resolve().parents[1] / "app" / "static"
        if sys.platform == "win32":
            root.iconbitmap(default=str(assets / "h-logsen.ico"))
        else:
            self.icon = tk.PhotoImage(master=root, file=str(assets / "h-logsen.png"))
            root.iconphoto(True, self.icon)
        self.client = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.role = None
        self.jobs = {}
        self.log_rows = []
        self.records = {}
        self.origin = tk.StringVar(value="http://127.0.0.1:5000")
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.selection = tk.StringVar()
        self.search = tk.StringVar()
        self.sort = tk.StringVar(value="desc")
        self.limit = tk.IntVar(value=25)
        self.progress = tk.DoubleVar(value=0)
        self.auto = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Sign in to see authorized datasets.")
        self.mutations = []
        self.connected_widgets = []
        self.build()
        self.update_controls()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(1800, self.poll_job)

    def build(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Exit", command=self.close)
        menu.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo(
            APP_NAME, "Select a granted dataset to read its real log records.", parent=self.root))
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menu)

        login = ttk.LabelFrame(self.root, text="Connection", padding=8)
        login.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")
        for col, (label, var) in enumerate((("Server", self.origin), ("Username", self.username),
                                            ("Password", self.password))):
            ttk.Label(login, text=label).grid(row=0, column=col, sticky="w")
            entry = ttk.Entry(login, textvariable=var, show="*" if col == 2 else "")
            entry.grid(row=1, column=col, padx=(0, 8), sticky="ew")
            login.columnconfigure(col, weight=1)
            if col == 1:
                entry.focus_set()
        self.login_button = ttk.Button(login, text="Sign in", command=self.sign_in)
        self.login_button.grid(row=1, column=3)

        datasets = ttk.LabelFrame(self.root, text="Datasets", padding=8)
        datasets.grid(row=1, column=0, padx=10, pady=4, sticky="ew")
        datasets.columnconfigure(0, weight=1)
        self.dataset_picker = ttk.Combobox(datasets, textvariable=self.selection, state="readonly")
        self.dataset_picker.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.dataset_picker.bind("<<ComboboxSelected>>", self.select_dataset)
        refresh = ttk.Button(datasets, text="Refresh", command=self.refresh_datasets)
        refresh.grid(row=0, column=1)
        self.connected_widgets.append(refresh)
        for col, (label, roles, callback) in enumerate((
            ("New", {"manager", "admin"}, self.new_dataset),
            ("Rename", {"manager", "admin"}, self.rename_dataset),
            ("Delete empty", {"admin"}, self.remove_dataset),
        ), start=2):
            button = ttk.Button(datasets, text=label, command=callback)
            button.grid(row=0, column=col, padx=(4, 0))
            self.mutations.append((button, roles))
        Tooltip(self.mutations[-1][0], "The server checks that the dataset has no related records.")

        tabs = ttk.Notebook(self.root)
        tabs.grid(row=2, column=0, padx=10, pady=4, sticky="nsew")
        logs = ttk.Frame(tabs, padding=8)
        jobs = ttk.Frame(tabs, padding=8)
        tabs.add(logs, text="Logs")
        tabs.add(jobs, text="Import progress")
        logs.columnconfigure(0, weight=1)
        logs.rowconfigure(1, weight=1)
        filters = ttk.LabelFrame(logs, text="Search and display", padding=6)
        filters.grid(row=0, column=0, sticky="ew")
        filters.columnconfigure(0, weight=1)
        ttk.Entry(filters, textvariable=self.search).grid(row=0, column=0, sticky="ew", padx=4)
        ttk.Spinbox(filters, from_=1, to=100, textvariable=self.limit, width=5).grid(row=0, column=1)
        for col, (label, value) in enumerate((("Newest", "desc"), ("Oldest", "asc")), 2):
            ttk.Radiobutton(filters, text=label, variable=self.sort, value=value).grid(row=0, column=col)
        load = ttk.Button(filters, text="Read logs", command=self.read_logs)
        load.grid(row=0, column=4, padx=4)
        export = ttk.Button(filters, text="Save visible CSV", command=self.export_logs)
        export.grid(row=0, column=5)
        self.connected_widgets.extend((load, export))
        self.logs = scrolledtext.ScrolledText(logs, wrap="word", state="disabled", relief="sunken")
        self.logs.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        jobs.columnconfigure(0, weight=1)
        self.upload_button = ttk.Button(jobs, text="Upload BGL file", command=self.upload)
        self.upload_button.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(jobs, text="Refresh automatically", variable=self.auto).grid(row=1, column=0, sticky="w")
        check = ttk.Button(jobs, text="Check import", command=self.check_import)
        check.grid(row=1, column=1, padx=4)
        self.connected_widgets.append(check)
        ttk.Progressbar(jobs, variable=self.progress, maximum=100).grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)
        self.canvas = tk.Canvas(jobs, height=48, background="#ffffff", highlightthickness=1)
        self.canvas.grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Label(self.root, textvariable=self.status, wraplength=720).grid(row=3, column=0, padx=10, pady=6, sticky="w")

    def update_controls(self):
        busy = self.future is not None
        connected = self.client is not None and not busy
        self.login_button.configure(state="disabled" if busy else "normal")
        self.dataset_picker.configure(state="readonly" if connected else "disabled")
        for widget in self.connected_widgets:
            widget.configure(state="normal" if connected else "disabled")
        for button, roles in self.mutations:
            button.configure(state="normal" if connected and self.role in roles else "disabled")
        self.upload_button.configure(state="normal" if connected and self.role in {"analyst", "manager", "admin"} else "disabled")

    def run(self, work, on_success):
        if self.future is not None:
            return
        self.future = self.executor.submit(work)
        self.update_controls()
        self.status.set("Working…")
        self.root.after(40, lambda: self.collect(on_success))

    def collect(self, on_success):
        if not self.future.done():
            self.root.after(40, lambda: self.collect(on_success))
            return
        future, self.future = self.future, None
        self.update_controls()
        try:
            result = future.result()
        except (ApiError, OSError, ValueError) as error:
            self.status.set(str(error))
            return
        self.status.set("Ready.")
        on_success(result)

    def sign_in(self):
        origin, username, password = self.origin.get(), self.username.get(), self.password.get()
        self.password.set("")

        def connect():
            client = LogSenseClient(origin)
            try:
                return client, client.login(username, password)
            except Exception:
                client.session.close()
                raise

        def signed_in(result):
            if self.client:
                self.client.session.close()
            self.client, user = result
            self.role = user["role"]
            self.records.clear()
            self.jobs.clear()
            self.dataset_picker.configure(values=())
            self.selection.set("")
            self.select_dataset()
            self.refresh_datasets()

        self.run(connect, signed_in)

    def dataset_id(self):
        return self.records.get(self.selection.get())

    def refresh_datasets(self, preferred=None):
        current = preferred if preferred is not None else self.dataset_id()

        def display(rows):
            self.records = {f'{row["id"]} · {row["name"]}': row["id"] for row in rows}
            values = list(self.records)
            self.dataset_picker.configure(values=values)
            self.selection.set(next((k for k, v in self.records.items() if v == current), values[0] if values else ""))
            self.select_dataset()
            self.status.set(f"{len(values)} dataset(s) available on this page.")

        self.run(self.client.datasets, display)

    def select_dataset(self, _event=None):
        self.show_logs([])
        job = self.jobs.get(self.dataset_id())
        if job:
            self.show_job(job)
        else:
            self.progress.set(0)
            self.canvas.delete("all")

    def new_dataset(self):
        name = simpledialog.askstring("Register dataset", "Dataset name:", parent=self.root)
        if not name:
            return
        key = simpledialog.askstring("Register dataset", "Unique key (letters, digits, dot, dash, underscore):", parent=self.root)
        if key:
            self.run(lambda: self.client.create_dataset(name, key),
                     lambda row: self.refresh_datasets(row["id"]))

    def rename_dataset(self):
        dataset_id = self.dataset_id()
        if dataset_id is None:
            return
        name = simpledialog.askstring("Rename dataset", "New name:", parent=self.root)
        if name:
            self.run(lambda: self.client.rename_dataset(dataset_id, name),
                     lambda row: self.refresh_datasets(row["id"]))

    def remove_dataset(self):
        dataset_id = self.dataset_id()
        if dataset_id is not None and messagebox.askyesno(
                "Delete empty dataset", f"Delete {self.selection.get()} if it is empty?", parent=self.root):
            self.run(lambda: self.client.delete_dataset(dataset_id), lambda _: self.refresh_datasets())

    def read_logs(self):
        dataset_id = self.dataset_id()
        if dataset_id is None:
            self.status.set("Select a dataset.")
            return
        try:
            limit = self.limit.get()
            if not 1 <= limit <= 100:
                raise ValueError()
        except (ValueError, tk.TclError):
            self.status.set("Enter a page size from 1 to 100.")
            return
        query, sort = self.search.get(), self.sort.get()

        def fetch():
            interval = self.client.log_range(dataset_id)
            if not interval or not interval["start_time"]:
                return {"items": [], "count": 0}
            return self.client.logs(dataset_id, interval["start_time"], interval["end_time"],
                                    limit=limit, sort=sort, q=query)

        def display(page):
            self.show_logs(page["items"])
            self.status.set(f'{len(page["items"])} displayed · {page["count"]:,} matches in MySQL')

        self.run(fetch, display)

    def show_logs(self, rows):
        self.log_rows = rows
        self.logs.configure(state="normal")
        self.logs.delete("1.0", "end")
        for row in rows:
            self.logs.insert("end", f'{row["timestamp"]}  {row["severity"]}  {row["host"]}\n{row["message"]}\n\n')
        self.logs.configure(state="disabled")

    def export_logs(self):
        if not self.log_rows:
            self.status.set("Read log rows before saving.")
            return
        destination = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv",
                                                  filetypes=[("CSV", "*.csv")])
        if destination:
            self.run(lambda: write_log_csv(destination, self.log_rows),
                     lambda _: self.status.set(f"Saved {len(self.log_rows)} log rows."))

    def upload(self):
        dataset_id = self.dataset_id()
        if dataset_id is None:
            self.status.set("Select a dataset.")
            return
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("BGL text or CSV", "*.txt *.log *.csv")])
        if path:
            self.run(lambda: self.client.upload(dataset_id, path), self.show_job)

    def show_job(self, job):
        self.jobs[job["dataset_id"]] = job
        completed, total = job["processed_count"], job["total_lines"]
        self.progress.set(min(100, completed * 100 / total) if total else 0)
        state = job["state"]
        color = {"completed": "#087f5b", "failed": "#b02a37"}.get(state, "#1769a0")
        self.canvas.delete("all")
        self.canvas.create_oval(9, 14, 24, 29, fill=color, outline="")
        self.canvas.create_text(34, 22, anchor="w", text=f'Import {job["job_id"]}: {state} · {completed:,}/{total:,} lines')
        self.status.set(f'{state} · {job["parsed_events"]:,} parsed · {job["malformed_rows"]:,} malformed')

    def check_import(self):
        job = self.jobs.get(self.dataset_id())
        if job:
            self.run(lambda: self.client.upload_status(job["upload_id"]), self.show_job)

    def poll_job(self):
        job = self.jobs.get(self.dataset_id())
        if self.client and self.auto.get() and job and job["state"] in {"queued", "running"}:
            self.check_import()
        self.root.after(1800, self.poll_job)

    def close(self):
        if self.future is not None:
            messagebox.showwarning("Request in progress", "Wait for the current request to complete.", parent=self.root)
            return
        self.executor.shutdown(wait=False, cancel_futures=True)
        if self.client:
            self.client.session.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    Desktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
