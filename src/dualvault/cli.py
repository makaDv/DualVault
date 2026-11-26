"""Command-line interface."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dualvault import __version__, config, crypto, destinations, engine, logging_setup, scheduler
from dualvault.config import ConfigError, Destination, Source

log = logging.getLogger("dualvault")


def _load(args) -> config.Config:
    return config.load(args.config)


def _password(cfg: config.Config, interactive: bool, needed: bool, confirm: bool = False):
    if not needed:
        return None

    def no_prompt(_msg: str) -> str:
        raise ValueError(
            "A password is required but none is available non-interactively: set "
            "DUALVAULT_PASSWORD or settings.password_file"
        )

    return crypto.resolve_password(
        cfg.settings.password_file, prompt=None if interactive else no_prompt, confirm=confirm
    )


# ---------------------------------------------------------------- commands
def cmd_init(args) -> int:
    if args.config.exists() and not args.force:
        print(f"Configuration already exists: {args.config}")
        return 0
    config.save(config.Config(), args.config)
    print(f"Created {args.config}")
    print("Next: 'dualvault add-source NAME PATH' and 'dualvault add-dest NAME --path PATH'")
    return 0


def cmd_add_source(args) -> int:
    cfg = _load(args)
    path = Path(args.path).expanduser()
    if not path.is_dir():
        raise ConfigError(f"{path} is not a folder")
    cfg.sources = [s for s in cfg.sources if s.name != args.name]
    cfg.sources.append(Source(args.name, str(path.resolve()), args.exclude or []))
    config.save(cfg, args.config)
    print(f"Source '{args.name}' -> {path.resolve()}")
    return 0


def cmd_add_dest(args) -> int:
    cfg = _load(args)
    if bool(args.path) == bool(args.rclone):
        raise ConfigError("Specify exactly one of --path or --rclone")
    if args.path:
        dest = Destination(args.name, "local", path=str(Path(args.path).expanduser()))
    else:
        dest = Destination(args.name, "rclone", remote=args.rclone)
    cfg.destinations = [d for d in cfg.destinations if d.name != args.name]
    cfg.destinations.append(dest)
    config.save(cfg, args.config)
    print(f"Destination '{args.name}' added ({dest.type})")
    return 0


def cmd_remove(args) -> int:
    cfg = _load(args)
    if args.kind == "source":
        cfg.source(args.name)
        cfg.sources = [s for s in cfg.sources if s.name != args.name]
    else:
        cfg.destination(args.name)
        cfg.destinations = [d for d in cfg.destinations if d.name != args.name]
    config.save(cfg, args.config)
    print(f"Removed {args.kind} '{args.name}' (existing backups were not deleted)")
    return 0


def cmd_set(args) -> int:
    cfg = _load(args)
    for key in ("keep_last", "keep_daily", "keep_weekly", "keep_monthly"):
        value = getattr(args, key)
        if value is not None:
            setattr(cfg.retention, key, value)
    if args.encrypt is not None:
        cfg.settings.encrypt = args.encrypt
    if args.password_file is not None:
        cfg.settings.password_file = args.password_file
    if args.rclone_binary is not None:
        cfg.settings.rclone_binary = args.rclone_binary
    config.save(cfg, args.config)
    print("Settings saved")
    return 0


def cmd_show(args) -> int:
    cfg = _load(args)
    print(f"Config file: {args.config}")
    print(f"Log file:    {logging_setup.paths.log_dir() / logging_setup.LOG_FILE}")
    print(f"Encryption:  {'on' if cfg.settings.encrypt else 'off'}")
    r = cfg.retention
    print(
        f"Retention:   last={r.keep_last} daily={r.keep_daily} "
        f"weekly={r.keep_weekly} monthly={r.keep_monthly}"
    )
    print("Sources:")
    for s in cfg.sources:
        excl = f"  (exclude: {', '.join(s.exclude)})" if s.exclude else ""
        print(f"  - {s.name}: {s.path}{excl}")
    print("Destinations:")
    for d in cfg.destinations:
        print(f"  - {d.name}: {d.type} {d.path or d.remote}")
    return 0


def cmd_run(args) -> int:
    cfg = _load(args)
    pw = _password(cfg, not args.quiet, cfg.settings.encrypt, confirm=not args.quiet)
    report = engine.run_backup(
        cfg, pw, args.source or None, args.dest or None, do_prune=not args.no_prune
    )
    for err in report.errors:
        print(f"ERROR: {err}", file=sys.stderr)
    return report.exit_code()


def _dest(cfg, name):
    return destinations.build(cfg.destination(name), cfg.settings)


def cmd_list(args) -> int:
    cfg = _load(args)
    dests = [args.dest] if args.dest else [d.name for d in cfg.destinations]
    srcs = [args.source] if args.source else [s.name for s in cfg.sources]
    for dname in dests:
        dest = _dest(cfg, dname)
        try:
            dest.check()
        except destinations.DestinationUnavailable as exc:
            print(f"[{dname}] unavailable: {exc}")
            continue
        for sname in srcs:
            snaps = engine.list_snapshots(dest, sname)
            print(f"[{dname}] {sname}: {len(snaps)} snapshot(s)")
            for s in snaps:
                lock = " (encrypted)" if s.encrypted else ""
                print(f"    {s.created:%Y-%m-%d %H:%M:%S} UTC  {s.filename}{lock}")
    return 0


def cmd_prune(args) -> int:
    cfg = _load(args)
    dests = [args.dest] if args.dest else [d.name for d in cfg.destinations]
    for dname in dests:
        dest = _dest(cfg, dname)
        dest.check()
        for s in cfg.sources:
            removed = engine.prune(cfg, dest, s.name, dry_run=args.dry_run)
            print(
                f"[{dname}] {s.name}: {len(removed)} snapshot(s) "
                f"{'would be ' if args.dry_run else ''}deleted"
            )
    return 0


def _needs_password(cfg, dest, source, snapshot) -> bool:
    snap = engine._resolve_snapshot(dest, source, snapshot)
    return snap.encrypted


def cmd_verify(args) -> int:
    cfg = _load(args)
    dest = _dest(cfg, args.dest)
    dest.check()
    pw = _password(cfg, True, _needs_password(cfg, dest, args.source, args.snapshot))
    problems = engine.verify(dest, args.source, args.snapshot, pw)
    if problems:
        for p in problems:
            print(f"PROBLEM: {p}")
        return 1
    print("Snapshot is intact")
    return 0


def cmd_restore(args) -> int:
    cfg = _load(args)
    dest = _dest(cfg, args.dest)
    dest.check()
    pw = _password(cfg, True, _needs_password(cfg, dest, args.source, args.snapshot))
    count = engine.restore(dest, args.source, args.snapshot, Path(args.to), pw, args.force)
    print(f"Restored {count} files to {Path(args.to).resolve()}")
    return 0


def cmd_schedule(args) -> int:
    plan = scheduler.remove_plan() if args.remove else scheduler.build_plan(args.at)
    print(plan.description)
    for path, content in plan.files.items():
        print(f"\n--- {path} ---\n{content}")
    for cmd in plan.commands:
        print("$ " + " ".join(cmd))
    if not args.install:
        print("\nNothing changed. Re-run with --install to apply.")
        return 0
    scheduler.apply(plan)
    print("Done.")
    return 0


def cmd_gui(args) -> int:
    from dualvault import gui

    return gui.main(args.config)


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dualvault",
        description="Automatic, versioned backups to external drives and cloud storage.",
    )
    p.add_argument("--version", action="version", version=f"dualvault {__version__}")
    p.add_argument("--config", type=Path, default=None, help="config file path")
    p.add_argument("-v", "--verbose", action="store_true", help="show debug output")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="create an empty configuration")
    s.add_argument("--force", action="store_true", help="overwrite an existing config")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("add-source", help="add or replace a folder to back up")
    s.add_argument("name")
    s.add_argument("path")
    s.add_argument(
        "--exclude",
        action="append",
        metavar="GLOB",
        help="glob to skip, e.g. '*.tmp' or 'node_modules' (repeatable)",
    )
    s.set_defaults(func=cmd_add_source)

    s = sub.add_parser("add-dest", help="add or replace a backup destination")
    s.add_argument("name")
    s.add_argument("--path", help="local/external folder, e.g. E:\\Backups")
    s.add_argument("--rclone", metavar="REMOTE:PATH", help="rclone remote, e.g. gdrive:Backups")
    s.set_defaults(func=cmd_add_dest)

    s = sub.add_parser("remove", help="remove a source or destination from the config")
    s.add_argument("kind", choices=["source", "dest"])
    s.add_argument("name")
    s.set_defaults(func=cmd_remove)

    s = sub.add_parser("set", help="change retention and other settings")
    for key in ("keep_last", "keep_daily", "keep_weekly", "keep_monthly"):
        s.add_argument("--" + key.replace("_", "-"), dest=key, type=int)
    enc = s.add_mutually_exclusive_group()
    enc.add_argument("--encrypt", dest="encrypt", action="store_true", default=None)
    enc.add_argument("--no-encrypt", dest="encrypt", action="store_false")
    s.add_argument("--password-file", help="file holding the password for unattended runs")
    s.add_argument("--rclone-binary", help="path to the rclone executable")
    s.set_defaults(func=cmd_set)

    s = sub.add_parser("show", help="show the current configuration")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("run", help="back up now")
    s.add_argument("--source", action="append", help="only this source (repeatable)")
    s.add_argument("--dest", action="append", help="only this destination (repeatable)")
    s.add_argument("--no-prune", action="store_true", help="do not delete old snapshots")
    s.add_argument(
        "--quiet",
        action="store_true",
        help="non-interactive mode for scheduled runs (never prompts)",
    )
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("list", help="list snapshots")
    s.add_argument("--dest")
    s.add_argument("--source")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("prune", help="apply the retention policy now")
    s.add_argument("--dest")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_prune)

    for name, func, hlp in (
        ("verify", cmd_verify, "check a snapshot's integrity"),
        ("restore", cmd_restore, "restore a snapshot"),
    ):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("source")
        s.add_argument("--dest", required=True)
        s.add_argument("--snapshot", default="latest", help="file name or 'latest'")
        if name == "restore":
            s.add_argument("--to", required=True, help="target folder")
            s.add_argument("--force", action="store_true", help="allow a non-empty target")
        s.set_defaults(func=func)

    s = sub.add_parser("schedule", help="run backups automatically every day")
    s.add_argument("--at", default="02:00", help="time of day HH:MM (default 02:00)")
    s.add_argument("--install", action="store_true", help="actually register the task")
    s.add_argument("--remove", action="store_true", help="unregister the task")
    s.set_defaults(func=cmd_schedule)

    s = sub.add_parser("gui", help="open the graphical interface")
    s.set_defaults(func=cmd_gui)
    return p


def main(argv: list[str] | None = None) -> int:
    from dualvault import paths

    args = build_parser().parse_args(argv)
    args.config = args.config or paths.default_config_path()
    level = "INFO"
    try:
        if args.config.exists():
            level = config.load(args.config).settings.log_level
    except ConfigError:
        pass
    logging_setup.setup(level, verbose=args.verbose)
    if getattr(args, "quiet", False):
        for handler in logging.getLogger().handlers:
            if type(handler) is logging.StreamHandler:
                handler.setLevel(logging.WARNING)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except (
        ConfigError,
        ValueError,
        FileNotFoundError,
        FileExistsError,
        OSError,
        engine.LockedError,
        crypto.DecryptionError,
        destinations.DestinationUnavailable,
    ) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
