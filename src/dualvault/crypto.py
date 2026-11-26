"""Streaming authenticated encryption for snapshot archives.

File format (all integers big-endian)::

    magic      6 bytes   b"DVENC1"
    log2_n     1 byte    scrypt cost parameter N = 2**log2_n
    r          1 byte    scrypt r
    p          1 byte    scrypt p
    salt      16 bytes
    prefix     7 bytes   random nonce prefix
    then repeated chunks:
      length   4 bytes   length of the ciphertext that follows
      data     n bytes   AES-256-GCM(chunk) incl. 16-byte tag

Each chunk nonce is ``prefix || counter (4 bytes) || last_flag (1 byte)``
(the STREAM construction), and the header is bound as associated data.
This detects tampering, reordering and truncation. The password is never
stored; the key is derived with scrypt.
"""

from __future__ import annotations

import os
import struct
from collections.abc import Callable
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"DVENC1"
SUFFIX = ".dvenc"
CHUNK_SIZE = 1024 * 1024
SALT_LEN = 16
PREFIX_LEN = 7
HEADER_LEN = len(MAGIC) + 3 + SALT_LEN + PREFIX_LEN
DEFAULT_LOG2_N, DEFAULT_R, DEFAULT_P = 17, 8, 1
MAX_CHUNK_CT = CHUNK_SIZE + 16


class DecryptionError(Exception):
    """Wrong password or corrupted/tampered file."""


def _derive_key(password: str, salt: bytes, log2_n: int, r: int, p: int) -> bytes:
    if not password:
        raise ValueError("Empty password")
    if not 14 <= log2_n <= 22 or not 1 <= r <= 32 or not 1 <= p <= 16:
        raise DecryptionError("Unsupported key-derivation parameters in header")
    kdf = Scrypt(salt=salt, length=32, n=2**log2_n, r=r, p=p)
    return kdf.derive(password.encode("utf-8"))


def _nonce(prefix: bytes, counter: int, last: bool) -> bytes:
    if counter >= 2**32:
        raise ValueError("File too large for this format")
    return prefix + struct.pack(">IB", counter, 1 if last else 0)


def encrypt_file(
    src: Path,
    dst: Path,
    password: str,
    *,
    log2_n: int = DEFAULT_LOG2_N,
    r: int = DEFAULT_R,
    p: int = DEFAULT_P,
) -> None:
    salt = os.urandom(SALT_LEN)
    prefix = os.urandom(PREFIX_LEN)
    header = MAGIC + bytes([log2_n, r, p]) + salt + prefix
    aead = AESGCM(_derive_key(password, salt, log2_n, r, p))
    with src.open("rb") as fin, dst.open("wb") as fout:
        fout.write(header)
        counter = 0
        chunk = fin.read(CHUNK_SIZE)
        while True:
            nxt = fin.read(CHUNK_SIZE)
            last = not nxt
            ct = aead.encrypt(_nonce(prefix, counter, last), chunk, header)
            fout.write(struct.pack(">I", len(ct)))
            fout.write(ct)
            if last:
                break
            chunk = nxt
            counter += 1


def decrypt_file(src: Path, dst: Path, password: str) -> None:
    with src.open("rb") as fin:
        header = fin.read(HEADER_LEN)
        if len(header) != HEADER_LEN or not header.startswith(MAGIC):
            raise DecryptionError("Not a DualVault encrypted file")
        log2_n, r, p = header[6], header[7], header[8]
        salt = header[9 : 9 + SALT_LEN]
        prefix = header[9 + SALT_LEN :]
        aead = AESGCM(_derive_key(password, salt, log2_n, r, p))
        tmp = dst.with_name(dst.name + ".partial")
        try:
            with tmp.open("wb") as fout:
                counter = 0
                while True:
                    raw_len = fin.read(4)
                    if len(raw_len) != 4:
                        raise DecryptionError("File is truncated")
                    (length,) = struct.unpack(">I", raw_len)
                    if length > MAX_CHUNK_CT or length < 16:
                        raise DecryptionError("Corrupted chunk length")
                    ct = fin.read(length)
                    if len(ct) != length:
                        raise DecryptionError("File is truncated")
                    last = fin.peek(1) == b""  # nothing after this chunk
                    try:
                        pt = aead.decrypt(_nonce(prefix, counter, last), ct, header)
                    except InvalidTag:
                        raise DecryptionError(
                            "Decryption failed: wrong password or corrupted file"
                        ) from None
                    fout.write(pt)
                    if last:
                        break
                    counter += 1
            os.replace(tmp, dst)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise


def resolve_password(
    password_file: str = "",
    prompt: Callable[[str], str] | None = None,
    confirm: bool = False,
) -> str:
    """Get the password from DUALVAULT_PASSWORD, a password file, or an interactive prompt."""
    env = os.environ.get("DUALVAULT_PASSWORD")
    if env:
        return env
    if password_file:
        path = Path(password_file).expanduser()
        text = path.read_text(encoding="utf-8").splitlines()
        if not text or not text[0]:
            raise ValueError(f"Password file {path} is empty")
        return text[0]
    if prompt is None:
        import getpass

        prompt = getpass.getpass
    pw = prompt("Encryption password: ")
    if not pw:
        raise ValueError("Empty password")
    if confirm and prompt("Repeat password: ") != pw:
        raise ValueError("Passwords do not match")
    return pw
