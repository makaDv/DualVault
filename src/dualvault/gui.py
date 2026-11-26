"""Minimal Tkinter GUI to edit the configuration and run a backup."""

from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path

from dualvault import config, engine, logging_setup, paths
from dualvault.config import ConfigError, Destination, Source

log = logging.getLogger(__name__)


class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__(logging.INFO)
        self.q = q
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(self.format(record))


def main(config_path: Path | None = None) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    config_path = config_path or paths.default_config_path()
    logging_setup.setup()
    try:
        cfg = config.load(config_path) if config_path.exists() else config.Config()
    except ConfigError as exc:
        messagebox.showerror("DualVault", str(exc))
        return 1

    root = tk.Tk()
    root.title("DualVault")
    root.geometry("760x560")
    log_q: queue.Queue = queue.Queue()
    logging.getLogger().addHandler(_QueueHandler(log_q))

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8, pady=8)

    # ---- sources / destinations lists
    def make_list_tab(title: str):
        frame = ttk.Frame(nb, padding=8)
        nb.add(frame, text=title)
        lb = tk.Listbox(frame, height=12)
        lb.pack(fill="both", expand=True)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=6)
        return lb, buttons

    src_lb, src_btns = make_list_tab("Sources")
    dst_lb, dst_btns = make_list_tab("Destinations")

    def refresh() -> None:
        src_lb.delete(0, "end")
        for s in cfg.sources:
            src_lb.insert("end", f"{s.name}: {s.path}")
        dst_lb.delete(0, "end")
        for d in cfg.destinations:
            dst_lb.insert("end", f"{d.name}: [{d.type}] {d.path or d.remote}")

    def ask_name(kind: str) -> str | None:
        name = simpledialog.askstring("DualVault", f"Name for this {kind} (letters, digits, - _):")
        if not name:
            return None
        try:
            return config.validate_name(name.strip(), kind)
        except ConfigError as exc:
            messagebox.showerror("DualVault", str(exc))
            return None

    def add_source() -> None:
        folder = filedialog.askdirectory(title="Folder to back up")
        if not folder:
            return
        name = ask_name("source")
        if not name:
            return
        excl = simpledialog.askstring("DualVault", "Exclude patterns, comma separated (optional):")
        patterns = [p.strip() for p in (excl or "").split(",") if p.strip()]
        cfg.sources = [s for s in cfg.sources if s.name != name]
        cfg.sources.append(Source(name, folder, patterns))
        refresh()

    def add_local_dest() -> None:
        folder = filedialog.askdirectory(title="Backup folder (e.g. on an external drive)")
        name = folder and ask_name("destination")
        if name:
            cfg.destinations = [d for d in cfg.destinations if d.name != name]
            cfg.destinations.append(Destination(name, "local", path=folder))
            refresh()

    def add_rclone_dest() -> None:
        remote = simpledialog.askstring(
            "DualVault",
            "rclone remote and folder (e.g. gdrive:Backups/DualVault).\n"
            "Configure the remote first with 'rclone config'.",
        )
        name = remote and ask_name("destination")
        if name:
            cfg.destinations = [d for d in cfg.destinations if d.name != name]
            cfg.destinations.append(Destination(name, "rclone", remote=remote.strip()))
            refresh()

    def remove_selected(lb, attr: str) -> None:
        sel = lb.curselection()
        if sel:
            items = getattr(cfg, attr)
            del items[sel[0]]
            refresh()

    ttk.Button(src_btns, text="Add folder...", command=add_source).pack(side="left")
    ttk.Button(src_btns, text="Remove", command=lambda: remove_selected(src_lb, "sources")).pack(
        side="left", padx=4
    )
    ttk.Button(dst_btns, text="Add local/external folder...", command=add_local_dest).pack(
        side="left"
    )
    ttk.Button(dst_btns, text="Add rclone remote...", command=add_rclone_dest).pack(
        side="left", padx=4
    )
    ttk.Button(
        dst_btns, text="Remove", command=lambda: remove_selected(dst_lb, "destinations")
    ).pack(side="left")

    # ---- settings
    st = ttk.Frame(nb, padding=8)
    nb.add(st, text="Settings")
    ret_vars = {}
    for row, key in enumerate(("keep_last", "keep_daily", "keep_weekly", "keep_monthly")):
        ttk.Label(st, text=key.replace("_", " ").capitalize()).grid(row=row, column=0, sticky="w")
        var = tk.IntVar(value=getattr(cfg.retention, key))
        ttk.Spinbox(st, from_=0, to=999, textvariable=var, width=6).grid(row=row, column=1)
        ret_vars[key] = var
    enc_var = tk.BooleanVar(value=cfg.settings.encrypt)
    ttk.Checkbutton(st, text="Encrypt backups (password is never stored)", variable=enc_var).grid(
        row=5, column=0, columnspan=2, sticky="w", pady=8
    )

    def collect() -> bool:
        try:
            for key, var in ret_vars.items():
                setattr(cfg.retention, key, int(var.get()))
            cfg.settings.encrypt = bool(enc_var.get())
            cfg.validate()
            return True
        except (ConfigError, tk.TclError, ValueError) as exc:
            messagebox.showerror("DualVault", str(exc))
            return False

    def save() -> None:
        if collect():
            config.save(cfg, config_path)
            log.info("Configuration saved to %s", config_path)

    # ---- log + actions
    lg = ttk.Frame(nb, padding=8)
    nb.add(lg, text="Log")
    text = tk.Text(lg, height=20, state="disabled", wrap="word")
    text.pack(fill="both", expand=True)

    def pump_log() -> None:
        while not log_q.empty():
            text.configure(state="normal")
            text.insert("end", log_q.get() + "\n")
            text.see("end")
            text.configure(state="disabled")
        root.after(300, pump_log)

    bar = ttk.Frame(root, padding=(8, 0, 8, 8))
    bar.pack(fill="x")
    run_btn = ttk.Button(bar, text="Back up now")
    status = ttk.Label(bar, text="")

    def run_now() -> None:
        if not collect():
            return
        password = None
        if cfg.settings.encrypt:
            password = simpledialog.askstring("DualVault", "Encryption password:", show="*")
            if not password:
                return
            again = simpledialog.askstring("DualVault", "Repeat password:", show="*")
            if again != password:
                messagebox.showerror("DualVault", "Passwords do not match")
                return
        nb.select(lg)
        run_btn.state(["disabled"])
        status.configure(text="Running...")

        def worker() -> None:
            try:
                report = engine.run_backup(cfg, password)
                msg = "Done" if report.ok else f"Finished with {len(report.errors)} error(s)"
            except Exception as exc:
                log.error("%s", exc)
                msg = "Failed"
            root.after(0, lambda: (status.configure(text=msg), run_btn.state(["!disabled"])))

        threading.Thread(target=worker, daemon=True).start()

    run_btn.configure(command=run_now)
    ttk.Button(bar, text="Save settings", command=save).pack(side="left")
    run_btn.pack(side="left", padx=6)
    status.pack(side="left", padx=6)
    ttk.Label(bar, text=f"Log: {paths.log_dir()}").pack(side="right")

    refresh()
    pump_log()
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
