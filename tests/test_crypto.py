import os

import pytest

from dualvault import crypto


@pytest.mark.parametrize("size", [0, 10, crypto.CHUNK_SIZE, crypto.CHUNK_SIZE * 2 + 5])
def test_roundtrip(tmp_path, size):
    src = tmp_path / "in"
    src.write_bytes(os.urandom(size))
    enc, out = tmp_path / "enc", tmp_path / "out"
    crypto.encrypt_file(src, enc, "s3cret")
    crypto.decrypt_file(enc, out, "s3cret")
    assert out.read_bytes() == src.read_bytes()


def test_wrong_password(tmp_path):
    src = tmp_path / "in"
    src.write_bytes(b"data")
    crypto.encrypt_file(src, tmp_path / "enc", "right")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_file(tmp_path / "enc", tmp_path / "out", "wrong")
    assert not (tmp_path / "out").exists()


def test_truncation_detected(tmp_path):
    src = tmp_path / "in"
    src.write_bytes(os.urandom(crypto.CHUNK_SIZE * 2 + 100))
    enc = tmp_path / "enc"
    crypto.encrypt_file(src, enc, "pw")
    data = enc.read_bytes()
    # drop the final chunk entirely (cut at a chunk boundary)
    first_len = int.from_bytes(data[crypto.HEADER_LEN : crypto.HEADER_LEN + 4], "big")
    cut = crypto.HEADER_LEN + 4 + first_len
    enc.write_bytes(data[:cut])
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_file(enc, tmp_path / "out", "pw")


def test_tamper_detected(tmp_path):
    src = tmp_path / "in"
    src.write_bytes(b"x" * 1000)
    enc = tmp_path / "enc"
    crypto.encrypt_file(src, enc, "pw")
    data = bytearray(enc.read_bytes())
    data[-1] ^= 1
    enc.write_bytes(bytes(data))
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_file(enc, tmp_path / "out", "pw")


def test_resolve_password_sources(tmp_path, monkeypatch):
    pwfile = tmp_path / "pw.txt"
    pwfile.write_text("fromfile\n", encoding="utf-8")
    assert crypto.resolve_password(str(pwfile)) == "fromfile"
    monkeypatch.setenv("DUALVAULT_PASSWORD", "fromenv")
    assert crypto.resolve_password(str(pwfile)) == "fromenv"
    monkeypatch.delenv("DUALVAULT_PASSWORD")
    answers = iter(["a", "b"])
    with pytest.raises(ValueError):
        crypto.resolve_password(prompt=lambda _m: next(answers), confirm=True)
