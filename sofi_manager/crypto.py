"""
crypto.py — symmetric encryption for sensitive fields stored in bots.json.

Tokens are wrapped as ``enc:v1:<urlsafe-b64>``. Plaintext (legacy format)
is detected by the absence of the ``enc:v1:`` prefix and returned
unchanged on read, which gives free in-place migration: any subsequent
``save_bots()`` call rewrites everything as ciphertext.

Key storage:
  1. OS keyring (``service="sofi-manager"``, ``username="fernet-key"``).
  2. Fallback file ``<USER_DATA>/key`` — Windows ``%APPDATA%/sofi-manager/``,
     POSIX ``~/.config/sofi-manager/``, ``chmod 600`` on POSIX.
  3. Generate a new Fernet key, store via the highest tier that worked.

The bots.json file never contains the key, only ciphertext.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_MARKER = "enc:v1:"
_KEYRING_SERVICE = "sofi-manager"
_KEYRING_USER = "fernet-key"

# Cached cipher — built lazily so importing this module is side-effect-free.
_cipher: Fernet | None = None


def _user_data_dir() -> Path:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return root / "sofi-manager"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg) if xdg else Path.home() / ".config"
    return root / "sofi-manager"


def _key_file() -> Path:
    return _user_data_dir() / "key"


def _try_keyring_get() -> bytes | None:
    try:
        import keyring

        value = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
    except Exception:
        return None
    if not value:
        return None
    return value.encode("ascii")


def _try_keyring_set(key: bytes) -> bool:
    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, key.decode("ascii"))
        return True
    except Exception:
        return False


def _read_key_file() -> bytes | None:
    path = _key_file()
    if not path.exists():
        return None
    try:
        return path.read_bytes().strip()
    except OSError:
        return None


def _write_key_file(key: bytes) -> None:
    path = _key_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    if os.name != "nt":
        # Best-effort: restrict to owner. On Windows, NTFS ACLs default
        # to per-user %APPDATA% which is already user-private.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _load_or_create_key() -> bytes:
    key = _try_keyring_get()
    if key:
        return key
    key = _read_key_file()
    if key:
        # Backfill to keyring if it became available since first run.
        _try_keyring_set(key)
        return key
    key = Fernet.generate_key()
    if not _try_keyring_set(key):
        _write_key_file(key)
    return key


def _get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        _cipher = Fernet(_load_or_create_key())
    return _cipher


def set_cipher_for_tests(cipher: Fernet | None) -> None:
    """Inject a Fernet instance (or None to reset). Test-only hook."""
    global _cipher
    _cipher = cipher


def is_encrypted(value: str) -> bool:
    return value.startswith(_MARKER)


def encrypt_token(plain: str) -> str:
    if not plain or is_encrypted(plain):
        return plain
    token = _get_cipher().encrypt(plain.encode("utf-8")).decode("ascii")
    return _MARKER + token


def decrypt_token(stored: str) -> str:
    if not stored or not is_encrypted(stored):
        return stored
    payload = stored[len(_MARKER) :]
    try:
        return _get_cipher().decrypt(payload.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        # Surfacing this clearly matters: most likely cause is a missing
        # or rotated key (e.g. user restored bots.json on a new machine).
        raise RuntimeError(
            "Cannot decrypt token: encryption key missing or mismatched. "
            "If you restored bots.json from a backup, also restore the key "
            f"from {_key_file()} or the OS keyring."
        ) from e
