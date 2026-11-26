from datetime import datetime, timedelta, timezone

import pytest

from dualvault import cli, config, engine
from dualvault.config import Config, ConfigError, Destination, Retention, Source
from dualvault.destinations import LocalDestination


def make_config(sample_tree, dest_dir, **settings):
    cfg = Config(
        retention=Retention(keep_last=2, keep_daily=0, keep_weekly=0, keep_monthly=0),
        sources=[Source("data", str(sample_tree), ["*.tmp"])],
        destinations=[Destination("ext", "local", path=str(dest_dir))],
    )
    for k, v in settings.items():
        setattr(cfg.settings, k, v)
    return cfg.validate()


def test_backup_rotation_restore(tmp_path, sample_tree):
    cfg = make_config(sample_tree, tmp_path / "backups")
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    for i in range(4):
        report = engine.run_backup(cfg, now=start + timedelta(minutes=i))
        assert report.ok, report.errors
    dest = LocalDestination("ext", str(tmp_path / "backups"))
    snaps = engine.list_snapshots(dest, "data")
    assert len(snaps) == 2
    assert snaps[0].created == start + timedelta(minutes=3)
    out = tmp_path / "restored"
    assert engine.restore(dest, "data", "latest", out, None) == 3
    assert (out / "docs" / "a.txt").read_text(encoding="utf-8") == "hello"


def test_encrypted_backup(tmp_path, sample_tree):
    cfg = make_config(sample_tree, tmp_path / "backups", encrypt=True)
    with pytest.raises(ValueError):
        engine.run_backup(cfg, None)
    assert engine.run_backup(cfg, "pw").ok
    dest = LocalDestination("ext", str(tmp_path / "backups"))
    snap = engine.list_snapshots(dest, "data")[0]
    assert snap.encrypted
    assert engine.verify(dest, "data", "latest", "pw") == []
    from dualvault.crypto import DecryptionError

    with pytest.raises(DecryptionError):
        engine.verify(dest, "data", "latest", "nope")


def test_unavailable_destination_is_skipped(tmp_path, sample_tree):
    cfg = make_config(sample_tree, tmp_path / "backups")
    cfg.destinations.append(Destination("gone", "rclone", remote="nosuchremote:x"))
    cfg.settings.rclone_binary = "definitely-not-rclone-binary"
    report = engine.run_backup(cfg)
    assert report.ok
    assert report.exit_code() == 2
    assert any("gone" in s for s in report.skipped)


def test_lock_prevents_concurrent_runs(tmp_path):
    with (
        engine.run_lock(tmp_path),
        pytest.raises(engine.LockedError),
        engine.run_lock(tmp_path),
    ):
        pass


def test_config_validation(tmp_path):
    with pytest.raises(ConfigError):
        config.validate_name("../bad", "source")
    with pytest.raises(ConfigError):
        Config.from_dict({"sources": [{"name": "a", "path": "x", "bogus": 1}]})
    with pytest.raises(ConfigError):
        Config(retention=Retention(0, 0, 0, 0)).validate()
    cfg = Config(sources=[Source("a", "/x")])
    path = tmp_path / "c.toml"
    config.save(cfg, path)
    assert config.load(path) == cfg


def test_cli_end_to_end(tmp_path, sample_tree, capsys):
    cfgp = str(tmp_path / "cfg.toml")
    dest = tmp_path / "ext"
    assert cli.main(["--config", cfgp, "init"]) == 0
    assert (
        cli.main(
            ["--config", cfgp, "add-source", "data", str(sample_tree), "--exclude", "node_modules"]
        )
        == 0
    )
    assert cli.main(["--config", cfgp, "add-dest", "ext", "--path", str(dest)]) == 0
    assert cli.main(["--config", cfgp, "set", "--keep-last", "3"]) == 0
    assert cli.main(["--config", cfgp, "run", "--quiet"]) == 0
    assert cli.main(["--config", cfgp, "list"]) == 0
    assert "1 snapshot(s)" in capsys.readouterr().out
    assert cli.main(["--config", cfgp, "verify", "data", "--dest", "ext"]) == 0
    out = tmp_path / "r"
    assert cli.main(["--config", cfgp, "restore", "data", "--dest", "ext", "--to", str(out)]) == 0
    assert (out / "skip.tmp").exists()
    assert not (out / "node_modules").exists()
    assert cli.main(["--config", cfgp, "add-dest", "bad name", "--path", "x"]) == 1


def test_cli_quiet_never_prompts(tmp_path, sample_tree, monkeypatch):
    cfgp = str(tmp_path / "cfg.toml")
    cli.main(["--config", cfgp, "init"])
    cli.main(["--config", cfgp, "add-source", "data", str(sample_tree)])
    cli.main(["--config", cfgp, "add-dest", "ext", "--path", str(tmp_path / "ext")])
    cli.main(["--config", cfgp, "set", "--encrypt"])
    monkeypatch.setattr("getpass.getpass", lambda *_: pytest.fail("prompted"))
    assert cli.main(["--config", cfgp, "run", "--quiet"]) == 1
    monkeypatch.setenv("DUALVAULT_PASSWORD", "pw")
    assert cli.main(["--config", cfgp, "run", "--quiet"]) == 0
