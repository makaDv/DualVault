import subprocess

import pytest

from dualvault import scheduler
from dualvault.destinations import rclone as rc
from dualvault.destinations.base import DestinationUnavailable


class FakeRun:
    def __init__(self, outputs):
        self.calls = []
        self.outputs = outputs

    def __call__(self, cmd, **kw):
        assert "shell" not in kw
        self.calls.append(cmd)
        out = self.outputs.get(cmd[1], ("", "", 0))
        return subprocess.CompletedProcess(cmd, out[2], out[0], out[1])


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(rc.shutil, "which", lambda b: "/usr/bin/rclone")
    run = FakeRun(
        {
            "listremotes": ("gdrive:\nother:\n", "", 0),
            "lsf": ("dualvault-docs-20260101T000000Z.zip\n", "", 0),
        }
    )
    monkeypatch.setattr(rc.subprocess, "run", run)
    return run


def test_rclone_commands(fake, tmp_path):
    d = rc.RcloneDestination("cloud", "gdrive:Backups/")
    d.check()
    f = tmp_path / "dualvault-docs-20260101T000000Z.zip"
    f.write_bytes(b"x")
    d.put(f, "docs", f.name)
    assert d.list("docs") == ["dualvault-docs-20260101T000000Z.zip"]
    d.delete("docs", f.name)
    copy = next(c for c in fake.calls if c[1] == "copyto")
    assert copy[-1] == "gdrive:Backups/docs/" + f.name
    assert "--" in copy
    assert fake.calls[-1][1:] == ["deletefile", "--", "gdrive:Backups/docs/" + f.name]


def test_rclone_missing_remote(fake):
    with pytest.raises(DestinationUnavailable):
        rc.RcloneDestination("cloud", "dropbox:x").check()


def test_rclone_rejects_unsafe_names(fake):
    d = rc.RcloneDestination("cloud", "gdrive:x")
    with pytest.raises(ValueError):
        d.list("../etc")
    with pytest.raises(ValueError):
        rc.RcloneDestination("cloud", "--config=/tmp/x:y")


def test_rclone_not_installed(monkeypatch):
    monkeypatch.setattr(rc.shutil, "which", lambda b: None)
    with pytest.raises(DestinationUnavailable):
        rc.RcloneDestination("cloud", "gdrive:x").check()


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_schedule_plans(platform):
    plan = scheduler.build_plan("03:15", platform)
    assert plan.commands
    text = " ".join(" ".join(c) for c in plan.commands) + " ".join(plan.files.values())
    assert "dualvault" in text
    assert "--quiet" in text
    with pytest.raises(ValueError):
        scheduler.build_plan("25:00", platform)
