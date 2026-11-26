# DualVault

**Automatic, versioned backups of your important folders to an external drive and/or the cloud — with logs, integrity checks, optional encryption and automatic cleanup of old versions.**

[![CI](https://github.com/makaDv/DualVault/actions/workflows/ci.yml/badge.svg)](https://github.com/makaDv/DualVault/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

- 📁 Back up any number of folders, with exclude patterns (`*.tmp`, `node_modules`, …)
- 💽 **Destinations**: external drives, NAS shares, any local folder — and **70+ cloud providers** (Google Drive, OneDrive, Dropbox, S3, Backblaze B2, …) through [rclone](https://rclone.org)
- 🕓 **Versioning**: every run creates a timestamped snapshot (ZIP + SHA-256 manifest)
- ♻️ **Retention**: keep the last *N* snapshots plus daily / weekly / monthly ones; older ones are deleted automatically
- 🔐 **Optional encryption**: AES-256-GCM, key derived from your password with scrypt; the password is never stored by DualVault
- ✅ **Integrity**: every upload is checksum-verified, `verify` re-checks any snapshot, restores are verified before extraction
- 📝 **Logs**: rotating log file + console output
- ⏰ **Scheduling**: one command registers a daily task (Windows Task Scheduler, systemd, launchd)
- 🖥️ CLI **and** a simple GUI · Windows, Linux, macOS · Python ≥ 3.10

> **Disclaimer.** DualVault is provided "as is", without warranty of any kind (see [LICENSE](LICENSE), sections 7–8). Always keep more than one copy of important data and **test your restores regularly**.

## Installation

Requires Python 3.10 or newer.

```bash
pip install git+https://github.com/makaDv/DualVault.git
```

Or from a clone:

```bash
git clone https://github.com/makaDv/DualVault.git
cd DualVault
pip install .
```

For cloud backups, also install [rclone](https://rclone.org/install/) and configure a remote once with `rclone config`. DualVault only calls rclone: your cloud credentials stay in rclone's own configuration and are never read or stored by DualVault.

## Quick start (CLI)

```bash
dualvault init
dualvault add-source documents "C:\Users\<you>\Documents" --exclude "*.tmp" --exclude "~$*"
dualvault add-dest external --path "E:\Backups"        # external drive
dualvault add-dest cloud --rclone "gdrive:Backups"     # optional, any rclone remote
dualvault set --keep-last 7 --keep-daily 7 --keep-weekly 4 --keep-monthly 12
dualvault run                                          # back up now
dualvault list                                         # see snapshots
dualvault schedule --at 02:00 --install                # back up every day at 02:00
```

Restore:

```bash
dualvault verify documents --dest external                  # check integrity
dualvault restore documents --dest external --to ./restored # latest snapshot
dualvault restore documents --dest external --snapshot dualvault-documents-20260101T020000Z.zip --to ./old
```

Run `dualvault --help` or `dualvault <command> --help` for every option.

### GUI

```bash
dualvault gui        # or: dualvault-gui
```

Add folders and destinations, set retention and encryption, then click **Back up now**. The log tab shows progress live.

## How it works

Each run, for every source folder:

1. A ZIP archive is created in a temporary folder, with a manifest of SHA-256 hashes of every file.
2. If encryption is on, the archive is encrypted (`.zip.dvenc`).
3. It is copied to every available destination as `<destination>/<source>/dualvault-<source>-<UTC timestamp>.zip[.dvenc]`, written to a `.partial` file first and verified before it becomes visible.
4. The retention policy deletes old snapshots of that source **on that destination only**.

If a destination is unavailable (drive unplugged, no internet, rclone missing) it is skipped with a warning and the others still run. Exit codes: `0` success, `2` success with warnings (skipped destination / unreadable files), `1` error.

Snapshots are plain ZIP files: unencrypted backups can be opened with any archive tool even without DualVault.

### Retention

| Setting        | Keeps                                                          |
|----------------|----------------------------------------------------------------|
| `keep_last`    | the N most recent snapshots                                    |
| `keep_daily`   | the newest snapshot of each of the last N days with a backup   |
| `keep_weekly`  | the newest snapshot of each of the last N ISO weeks            |
| `keep_monthly` | the newest snapshot of each of the last N months               |

A snapshot is kept if *any* rule selects it. Preview with `dualvault prune --dry-run`.

## Configuration

`dualvault init` creates a TOML file in your user folder:

| OS      | Config                                         | Logs                                     |
|---------|------------------------------------------------|------------------------------------------|
| Windows | `%APPDATA%\DualVault\config.toml`              | `%LOCALAPPDATA%\DualVault\logs\`         |
| Linux   | `~/.config/dualvault/config.toml`              | `~/.local/state/dualvault/logs/`         |
| macOS   | `~/Library/Application Support/DualVault/`     | same folder, `state/logs/`               |

Override with `--config PATH`, `DUALVAULT_CONFIG`, or `DUALVAULT_HOME` (puts everything in one folder — handy for a portable install). See [`examples/config.example.toml`](examples/config.example.toml) for all options. `dualvault show` prints the current configuration and file locations.

## Encryption

```bash
dualvault set --encrypt
```

- Algorithm: AES-256-GCM in 1 MiB authenticated chunks (detects tampering, reordering and truncation); key derived with scrypt (N=2¹⁷, r=8, p=1) and a random salt per file.
- Interactive runs ask for the password. **If you lose the password, encrypted backups cannot be recovered — by anyone.**
- For scheduled (unattended) runs, provide the password with the `DUALVAULT_PASSWORD` environment variable or `dualvault set --password-file PATH` (a file whose first line is the password). Protect that file with file-system permissions, and keep it **off** the backup destinations. Scheduled runs (`run --quiet`) never prompt; they fail with a clear log message if no password is available.

## Scheduling

`dualvault schedule --at HH:MM` shows what would be registered; add `--install` to apply it, `--remove --install` to remove it.

- **Windows**: a Task Scheduler task named `DualVault` for the current user.
- **Linux**: `~/.config/systemd/user/dualvault.{service,timer}` (with `Persistent=true`, so missed runs happen at next boot).
- **macOS**: `~/Library/LaunchAgents/io.github.dualvault.plist`.

## Security & privacy

- No telemetry, no network access other than the rclone commands you configure.
- Restores reject archive entries with absolute paths or `..` (path traversal) before writing anything.
- External commands are run without a shell.
- Report vulnerabilities privately: see [SECURITY.md](SECURITY.md).

## Development

```bash
git clone https://github.com/makaDv/DualVault.git && cd DualVault
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check .
```

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

Copyright DualVault contributors. Licensed under the [Apache License, Version 2.0](LICENSE). Third-party components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

rclone is a separate project (MIT license) that DualVault invokes as an external program; it is not bundled. Names of cloud providers are trademarks of their respective owners and are used only to describe compatibility.
