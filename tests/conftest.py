import pytest

from dualvault import crypto


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep every test away from the real user folders and environment."""
    home = tmp_path / "home"
    monkeypatch.setenv("DUALVAULT_HOME", str(home))
    monkeypatch.delenv("DUALVAULT_CONFIG", raising=False)
    monkeypatch.delenv("DUALVAULT_PASSWORD", raising=False)
    return home


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    """Use cheap scrypt parameters so the test suite stays fast."""
    monkeypatch.setattr(crypto, "DEFAULT_LOG2_N", 14)
    orig = crypto.encrypt_file

    def encrypt(src, dst, password, **kw):
        kw.setdefault("log2_n", 14)
        return orig(src, dst, password, **kw)

    monkeypatch.setattr(crypto, "encrypt_file", encrypt)


@pytest.fixture
def sample_tree(tmp_path):
    root = tmp_path / "data"
    (root / "docs" / "sub").mkdir(parents=True)
    (root / "docs" / "a.txt").write_text("hello", encoding="utf-8")
    (root / "docs" / "sub" / "b.bin").write_bytes(bytes(range(256)) * 1000)
    (root / "skip.tmp").write_text("temp", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "x.js").write_text("x", encoding="utf-8")
    return root
