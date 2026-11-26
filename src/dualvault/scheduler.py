"""Register DualVault with the operating system's task scheduler.

* Windows: Task Scheduler (``schtasks``), runs as the current user.
* Linux: systemd user timer.
* macOS: launchd user agent.

Nothing is installed unless ``install=True``; otherwise the commands/files
are only shown so the user can review them.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "DualVault"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass
class Plan:
    description: str
    files: dict[Path, str]
    commands: list[list[str]]


def _python_command() -> list[str]:
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            exe = pythonw
    return [str(exe), "-m", "dualvault", "run", "--quiet"]


def build_plan(at: str, platform: str | None = None) -> Plan:
    m = TIME_RE.match(at)
    if not m:
        raise ValueError("Time must be HH:MM (24h), e.g. 02:30")
    hour, minute = int(m[1]), int(m[2])
    platform = platform or sys.platform
    cmd = _python_command()

    if platform == "win32":
        tr = subprocess.list2cmdline(cmd)
        return Plan(
            f"Windows Task Scheduler task '{TASK_NAME}' daily at {at}",
            {},
            [["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", at, "/TN", TASK_NAME, "/TR", tr]],
        )
    if platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "io.github.dualvault.plist"
        args = "".join(f"\n    <string>{escape(a)}</string>" for a in cmd)
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>io.github.dualvault</string>
  <key>ProgramArguments</key>
  <array>{args}
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>{hour}</integer><key>Minute</key><integer>{minute}</integer></dict>
</dict>
</plist>
"""
        return Plan(
            f"launchd agent {plist} daily at {at}",
            {plist: content},
            [["launchctl", "unload", str(plist)], ["launchctl", "load", str(plist)]],
        )
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    exec_start = " ".join(_systemd_quote(a) for a in cmd)
    service = f"""[Unit]
Description=DualVault backup

[Service]
Type=oneshot
ExecStart={exec_start}
"""
    timer = f"""[Unit]
Description=Run DualVault backup daily

[Timer]
OnCalendar=*-*-* {hour:02d}:{minute:02d}:00
Persistent=true

[Install]
WantedBy=timers.target
"""
    return Plan(
        f"systemd user timer dualvault.timer daily at {at}",
        {unit_dir / "dualvault.service": service, unit_dir / "dualvault.timer": timer},
        [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", "dualvault.timer"],
        ],
    )


def _systemd_quote(arg: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=+-]+", arg):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'


def remove_plan(platform: str | None = None) -> Plan:
    platform = platform or sys.platform
    if platform == "win32":
        return Plan("Remove Windows task", {}, [["schtasks", "/Delete", "/F", "/TN", TASK_NAME]])
    if platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "io.github.dualvault.plist"
        return Plan(
            f"Unload {plist} (delete the file afterwards)",
            {},
            [["launchctl", "unload", str(plist)]],
        )
    return Plan(
        "Disable systemd timer",
        {},
        [["systemctl", "--user", "disable", "--now", "dualvault.timer"]],
    )


def apply(plan: Plan) -> None:
    for path, content in plan.files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for cmd in plan.commands:
        subprocess.run(cmd, check=cmd[:2] != ["launchctl", "unload"])
