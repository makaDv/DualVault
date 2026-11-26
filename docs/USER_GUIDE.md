# DualVault user guide

*[Versione italiana](GUIDA.md)*

DualVault automatically backs up your important folders to an external drive and/or the cloud, keeps several versions over time and deletes the oldest ones on its own.

> ⚠️ DualVault is provided "as is", without warranty. Always keep more than one copy of important data and **test a restore from time to time** to make sure your backups work.

---

## 1. How it works

Every time DualVault runs, for each configured folder it:

1. **Creates a snapshot**: a ZIP file with all the folder's files plus a list of each file's SHA-256 fingerprint, so damage can be detected later.
2. **Encrypts the snapshot** (only if encryption is on) with a password you choose.
3. **Copies the snapshot to every destination** (external drive, network folder, cloud) and checks the copy matches the original.
4. **Applies rotation**: keeps the most recent versions plus some daily, weekly and monthly ones; deletes the rest.

Each snapshot name contains the date and time (UTC), e.g.:

```
E:\Backups\documents\dualvault-documents-20260315T020000Z.zip
```

If a destination is unavailable (drive unplugged, no internet) it is skipped with a warning and the others still work.

---

## 2. Installation

### 2.1 Install Python

DualVault needs **Python 3.10 or newer**.

- **Windows**: download Python from <https://www.python.org/downloads/>. During setup **tick "Add python.exe to PATH"**.
- **macOS**: download from python.org or `brew install python`.
- **Linux**: usually preinstalled; the GUI may need `python3-tk` (e.g. `sudo apt install python3-tk`).

Check in a terminal (on Windows: *PowerShell*):

```
python --version
```

### 2.2 Install DualVault

```
pip install git+https://github.com/makaDv/DualVault.git
```

Without Git: download the ZIP from GitHub (*Code → Download ZIP*), extract it, open a terminal in the extracted folder and run `pip install .`.

Check:

```
dualvault --version
```

> 💡 If you get "command not found", use `python -m dualvault` instead of `dualvault` in every command of this guide.

---

## 3. First run with the GUI

```
dualvault gui
```

1. **Sources** → *Add folder...* → pick the folder to back up → give it a short name (letters, digits, `-` or `_`, e.g. `documents`) → optionally list files to skip, comma separated (e.g. `*.tmp, node_modules`).
2. **Destinations** → *Add local/external folder...* → pick a folder on the external drive (e.g. `E:\Backups`) → give it a name (e.g. `external`).
3. **Settings** → choose how many versions to keep (see §6) and optionally tick *Encrypt backups*.
4. Click **Save settings**.
5. Click **Back up now**. The **Log** tab shows progress.

---

## 4. First run from the command line

```
dualvault init
dualvault add-source documents "C:\Users\YourName\Documents" --exclude "*.tmp" --exclude "~$*"
dualvault add-dest external --path "E:\Backups"
dualvault run
dualvault list
```

| Command | What it does |
|---|---|
| `dualvault init` | create an empty configuration |
| `dualvault add-source NAME FOLDER` | add a folder to back up (`--exclude` repeatable) |
| `dualvault add-dest NAME --path FOLDER` | add a drive/folder destination |
| `dualvault add-dest NAME --rclone REMOTE:FOLDER` | add a cloud destination |
| `dualvault remove source NAME` / `remove dest NAME` | remove from the config (backups are kept) |
| `dualvault set ...` | change rotation, encryption, etc. |
| `dualvault show` | show configuration and file locations |
| `dualvault run` | back up now |
| `dualvault list` | list snapshots |
| `dualvault verify NAME --dest DEST` | check a snapshot's integrity |
| `dualvault restore NAME --dest DEST --to FOLDER` | restore |
| `dualvault prune --dry-run` | show what rotation would delete |
| `dualvault schedule --at HH:MM --install` | daily automatic backup |
| `dualvault gui` | open the GUI |

Help for any command: `dualvault <command> --help`.

---

## 5. Cloud backups (Google Drive, OneDrive, Dropbox, S3...)

DualVault uses **rclone**, a free tool supporting 70+ cloud services. Your credentials stay inside rclone; DualVault never sees them.

1. Install rclone: <https://rclone.org/install/> (Windows: `winget install Rclone.Rclone`).
2. Configure your service once:
   ```
   rclone config
   ```
   Choose `n` (new remote), name it (e.g. `gdrive`), pick the service and follow the prompts (a browser usually opens for sign-in).
3. Add the destination:
   ```
   dualvault add-dest cloud --rclone "gdrive:Backups/DualVault"
   ```

> 💡 Without rclone: if you have the Google Drive/OneDrive/Dropbox desktop app, use its synced folder as a local destination (`--path`).

---

## 6. Version rotation

```
dualvault set --keep-last 7 --keep-daily 7 --keep-weekly 4 --keep-monthly 12
```

| Setting | Keeps |
|---|---|
| `keep-last` | the last N snapshots |
| `keep-daily` | the newest of each of the last N days with a backup |
| `keep-weekly` | the newest of each of the last N weeks |
| `keep-monthly` | the newest of each of the last N months |

A snapshot is kept if **any** rule selects it. The values above give about one year of history in ~30 snapshots. Rotation works per folder and per destination.

Preview before changing rules: `dualvault prune --dry-run`.

---

## 7. Encryption

```
dualvault set --encrypt
```

New snapshots get the `.zip.dvenc` extension and are encrypted with AES-256-GCM. Manual runs ask for the password (twice).

> 🔑 **If you lose the password, encrypted backups cannot be recovered by anyone.** Keep it in a password manager.

For automatic (unattended) backups, provide the password with either:

- a file whose first line is the password: `dualvault set --password-file "/secure/path/dualvault-pw.txt"`. Restrict its permissions to your user and **do not store it on the backup drive**;
- the `DUALVAULT_PASSWORD` environment variable.

To go back to unencrypted backups: `dualvault set --no-encrypt`.

---

## 8. Automatic backups

```
dualvault schedule --at 02:00            # preview
dualvault schedule --at 02:00 --install  # enable
```

- **Windows**: creates the "DualVault" task in *Task Scheduler*. The PC must be on at that time.
- **Linux**: systemd user timer; missed runs happen at next boot.
- **macOS**: launchd agent.

Disable: `dualvault schedule --remove --install`.

> ⚠️ Plug in the external drive before backup time, otherwise that destination is skipped (noted in the log).

---

## 9. Restoring files

1. See your snapshots: `dualvault list`
2. (Optional) check integrity: `dualvault verify documents --dest external`
3. Restore **into a new, empty folder** (recommended, nothing gets overwritten):
   ```
   dualvault restore documents --dest external --to "C:\Restore"
   ```
   A specific version:
   ```
   dualvault restore documents --dest external --snapshot dualvault-documents-20260315T020000Z.zip --to "C:\Restore"
   ```
4. Check the files and copy them where you need them.

DualVault verifies the snapshot before extracting. If the target folder is not empty it stops; use `--force` only if you know what you are doing (files with the same name are overwritten).

> 💡 **Unencrypted** snapshots are regular ZIP files: any archive tool can open them, even without DualVault.

---

## 10. Configuration and log locations

| OS | Configuration | Logs |
|---|---|---|
| Windows | `%APPDATA%\DualVault\config.toml` | `%LOCALAPPDATA%\DualVault\logs\dualvault.log` |
| Linux | `~/.config/dualvault/config.toml` | `~/.local/state/dualvault/logs/` |
| macOS | `~/Library/Application Support/DualVault/` | `.../DualVault/state/logs/` |

`dualvault show` prints the exact paths. See [`examples/config.example.toml`](../examples/config.example.toml) for every option.

---

## 11. Troubleshooting

| Message / problem | Fix |
|---|---|
| `dualvault: command not found` | use `python -m dualvault ...` or add Python's *Scripts* folder to PATH |
| `Configuration not found` | run `dualvault init` first |
| `Destination ... skipped: Drive E:\ is not connected` | plug in the drive and run again |
| `rclone not found` | install rclone (§5) or set `dualvault set --rclone-binary PATH` |
| `rclone remote 'xxx:' is not configured` | run `rclone config` and use the same name |
| `A password is required but none is available non-interactively` | scheduled backup is encrypted but has no password: see §7 |
| `Decryption failed: wrong password or corrupted file` | wrong password or damaged file: try another snapshot |
| `Another backup is running` | wait for the running backup to finish |
| `Not enough free space` | free some space or reduce rotation |
| GUI does not open on Linux | install `python3-tk` |

`dualvault run` exit codes: `0` success, `2` success with warnings (skipped destination or unreadable files), `1` error. Details are always in the log.

---

## 12. Update and uninstall

```
pip install --upgrade git+https://github.com/makaDv/DualVault.git   # update
dualvault schedule --remove --install                               # remove schedule
pip uninstall dualvault                                             # uninstall
```

Uninstalling does not delete your backups or configuration (folders in §10).

---

## Support

- Bugs and ideas: [Issues](https://github.com/makaDv/DualVault/issues). **Remove personal paths and names** from logs before pasting.
- Security problems: **do not** open a public issue, see [SECURITY.md](../SECURITY.md).
