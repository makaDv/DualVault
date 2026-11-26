import zipfile

import pytest

from dualvault.restore import UnsafeArchiveError, extract_archive
from dualvault.snapshot import MANIFEST, SnapshotName, create_archive, verify_archive


def test_archive_excludes_and_verifies(tmp_path, sample_tree):
    arc = tmp_path / "a.zip"
    stats = create_archive(sample_tree, arc, "data", ["*.tmp", "node_modules"])
    assert stats.files == 2
    with zipfile.ZipFile(arc) as zf:
        names = set(zf.namelist())
    assert names == {"docs/a.txt", "docs/sub/b.bin", MANIFEST}
    assert verify_archive(arc) == []


def test_restore_roundtrip(tmp_path, sample_tree):
    arc = tmp_path / "a.zip"
    create_archive(sample_tree, arc, "data", ["*.tmp", "node_modules"])
    out = tmp_path / "restored"
    assert extract_archive(arc, out) == 2
    assert (out / "docs" / "sub" / "b.bin").read_bytes() == (
        sample_tree / "docs" / "sub" / "b.bin"
    ).read_bytes()
    with pytest.raises(FileExistsError):
        extract_archive(arc, out)
    assert extract_archive(arc, out, overwrite=True) == 2


def test_corruption_detected(tmp_path, sample_tree):
    arc = tmp_path / "a.zip"
    create_archive(sample_tree, arc, "data")
    with zipfile.ZipFile(arc) as zf:
        entries = {n: zf.read(n) for n in zf.namelist()}
    entries["docs/a.txt"] = b"changed"
    with zipfile.ZipFile(arc, "w") as zf:
        for n, d in entries.items():
            zf.writestr(n, d)
    assert verify_archive(arc) == ["checksum mismatch: docs/a.txt"]


@pytest.mark.parametrize(
    "evil", ["../evil.txt", "/abs.txt", "C:/win.txt", "a/../../x.txt", r"..\evil.txt"]
)
def test_path_traversal_rejected(tmp_path, evil):
    arc = tmp_path / "evil.zip"
    with zipfile.ZipFile(arc, "w") as zf:
        zf.writestr(MANIFEST, '{"files": {}}')
        zf.writestr(evil, "boom")
    out = tmp_path / "out"
    with pytest.raises(UnsafeArchiveError):
        extract_archive(arc, out)
    assert not any(out.iterdir())


def test_snapshot_name_roundtrip():
    s = SnapshotName.new("docs", encrypted=True)
    parsed = SnapshotName.parse(s.filename)
    assert parsed == s
    assert SnapshotName.parse("random.zip") is None
    assert SnapshotName.parse("dualvault-docs-20260101T000000Z.zip.partial") is None
