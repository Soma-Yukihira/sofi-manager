"""Unit tests for crypto.py — uses an injected Fernet so the OS keyring
and any fallback file on the developer's machine are never touched."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from sofi_manager import crypto


@pytest.fixture(autouse=True)
def _isolated_cipher() -> object:
    crypto.set_cipher_for_tests(Fernet(Fernet.generate_key()))
    yield
    crypto.set_cipher_for_tests(None)


def test_round_trip() -> None:
    plain = "mfa.abcdef.notarealtoken"
    blob = crypto.encrypt_token(plain)
    assert blob.startswith("enc:v1:")
    assert plain not in blob
    assert crypto.decrypt_token(blob) == plain


def test_decrypt_passthrough_on_plaintext() -> None:
    # Migration path: legacy plaintext tokens must round-trip unchanged
    # through decrypt_token so load_bots() keeps working pre-rewrite.
    legacy = "legacy_plain_token"
    assert crypto.decrypt_token(legacy) == legacy


def test_encrypt_skips_already_encrypted() -> None:
    blob = crypto.encrypt_token("x")
    assert crypto.encrypt_token(blob) == blob


def test_empty_string_passthrough() -> None:
    assert crypto.encrypt_token("") == ""
    assert crypto.decrypt_token("") == ""


def test_is_encrypted() -> None:
    assert not crypto.is_encrypted("plaintext")
    assert crypto.is_encrypted(crypto.encrypt_token("foo"))


def test_each_encryption_is_unique() -> None:
    a = crypto.encrypt_token("same")
    b = crypto.encrypt_token("same")
    assert a != b  # Fernet embeds an IV/timestamp
    assert crypto.decrypt_token(a) == crypto.decrypt_token(b) == "same"


def test_decrypt_with_wrong_key_raises_clearly() -> None:
    blob = crypto.encrypt_token("secret")
    crypto.set_cipher_for_tests(Fernet(Fernet.generate_key()))
    with pytest.raises(RuntimeError, match="Cannot decrypt token"):
        crypto.decrypt_token(blob)


# =====================================================================
# Key storage internals — keyring + filesystem fallback.
#
# These tests inject a fake `keyring` module via sys.modules so the real
# keyring daemon on the developer's machine is never touched, and use
# tmp_path for the file fallback.
# =====================================================================


class _FakeKeyring:
    """Stand-in for the keyring package. Backed by an in-memory dict, with
    optional flags to force get/set to raise, mirroring the real failure
    modes (no backend, permission denied, etc.)."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}
        self.raise_on_get = False
        self.raise_on_set = False

    def get_password(self, service: str, user: str) -> str | None:
        if self.raise_on_get:
            raise RuntimeError("simulated keyring backend error")
        return self.store.get((service, user))

    def set_password(self, service: str, user: str, value: str) -> None:
        if self.raise_on_set:
            raise RuntimeError("simulated keyring write error")
        self.store[(service, user)] = value


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> _FakeKeyring:
    fk = _FakeKeyring()
    module = types.ModuleType("keyring")
    module.get_password = fk.get_password  # type: ignore[attr-defined]
    module.set_password = fk.set_password  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "keyring", module)
    return fk


@pytest.fixture
def isolated_user_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect _user_data_dir to a tmp path so file-fallback writes never
    land in %APPDATA% / ~/.config on the developer's machine."""
    monkeypatch.setattr(crypto, "_user_data_dir", lambda: tmp_path)
    return tmp_path


# Tests that monkey-patch os.name to a *different* OS can't run cross-platform:
# pathlib resolves Path → WindowsPath / PosixPath at call time, and instantiating
# the wrong one for the actual host raises NotImplementedError. Each branch is
# therefore only exercised on its native host (Windows + Ubuntu CI between
# them give us full coverage of crypto._user_data_dir).


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows branch needs WindowsPath to be instantiable — only on Windows.",
)
def test_user_data_dir_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(crypto.os, "name", "nt")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert crypto._user_data_dir() == tmp_path / "Roaming" / "sofi-manager"


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows branch — see test above.",
)
def test_user_data_dir_windows_no_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(crypto.os, "name", "nt")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    result = crypto._user_data_dir()
    assert result == tmp_path / "AppData" / "Roaming" / "sofi-manager"


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX branch needs PosixPath to be instantiable — only on POSIX.",
)
def test_user_data_dir_posix_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(crypto.os, "name", "posix")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert crypto._user_data_dir() == tmp_path / "xdg" / "sofi-manager"


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX branch — see test above.",
)
def test_user_data_dir_posix_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(crypto.os, "name", "posix")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert crypto._user_data_dir() == tmp_path / ".config" / "sofi-manager"


def test_try_keyring_get_returns_bytes(fake_keyring: _FakeKeyring) -> None:
    fake_keyring.store[(crypto._KEYRING_SERVICE, crypto._KEYRING_USER)] = "abc"
    assert crypto._try_keyring_get() == b"abc"


def test_try_keyring_get_returns_none_when_empty(fake_keyring: _FakeKeyring) -> None:
    # Empty string from keyring counts as "no key stored", not as a real value.
    fake_keyring.store[(crypto._KEYRING_SERVICE, crypto._KEYRING_USER)] = ""
    assert crypto._try_keyring_get() is None


def test_try_keyring_get_swallows_backend_error(fake_keyring: _FakeKeyring) -> None:
    fake_keyring.raise_on_get = True
    assert crypto._try_keyring_get() is None


def test_try_keyring_get_returns_none_when_import_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No `keyring` in sys.modules and the real one not installed → import
    # raises inside the helper. Treated as "keyring unavailable".
    monkeypatch.setitem(sys.modules, "keyring", None)
    assert crypto._try_keyring_get() is None


def test_try_keyring_set_round_trips(fake_keyring: _FakeKeyring) -> None:
    assert crypto._try_keyring_set(b"my-key") is True
    assert fake_keyring.store[(crypto._KEYRING_SERVICE, crypto._KEYRING_USER)] == "my-key"


def test_try_keyring_set_returns_false_on_error(fake_keyring: _FakeKeyring) -> None:
    fake_keyring.raise_on_set = True
    assert crypto._try_keyring_set(b"my-key") is False


def test_read_key_file_returns_none_when_missing(isolated_user_dir: Path) -> None:
    assert crypto._read_key_file() is None


def test_read_key_file_strips_trailing_whitespace(isolated_user_dir: Path) -> None:
    (isolated_user_dir / "key").write_bytes(b"raw-key\n")
    assert crypto._read_key_file() == b"raw-key"


def test_read_key_file_swallows_oserror(
    isolated_user_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (isolated_user_dir / "key").write_bytes(b"raw-key")

    def boom(self: Path) -> bytes:
        raise OSError("simulated read error")

    monkeypatch.setattr(Path, "read_bytes", boom)
    assert crypto._read_key_file() is None


def test_write_key_file_creates_parent(isolated_user_dir: Path) -> None:
    # Remove the tmp directory so write must recreate it.
    isolated_user_dir.rmdir()
    crypto._write_key_file(b"new-key")
    assert (isolated_user_dir / "key").read_bytes() == b"new-key"


def test_write_key_file_chmods_on_posix(
    isolated_user_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(crypto.os, "name", "posix")
    chmod_calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        crypto.os, "chmod", lambda path, mode: chmod_calls.append((str(path), mode))
    )
    crypto._write_key_file(b"posix-key")
    assert chmod_calls and chmod_calls[0][1] == 0o600


def test_write_key_file_ignores_chmod_oserror(
    isolated_user_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(crypto.os, "name", "posix")

    def boom(path: str, mode: int) -> None:
        raise OSError("simulated chmod failure")

    monkeypatch.setattr(crypto.os, "chmod", boom)
    # Must not propagate — chmod is best-effort.
    crypto._write_key_file(b"posix-key")
    assert (isolated_user_dir / "key").read_bytes() == b"posix-key"


def test_load_or_create_key_uses_keyring_when_present(
    fake_keyring: _FakeKeyring, isolated_user_dir: Path
) -> None:
    fake_keyring.store[(crypto._KEYRING_SERVICE, crypto._KEYRING_USER)] = "from-keyring"
    assert crypto._load_or_create_key() == b"from-keyring"
    # File fallback must NOT have been touched.
    assert not (isolated_user_dir / "key").exists()


def test_load_or_create_key_backfills_keyring_from_file(
    fake_keyring: _FakeKeyring, isolated_user_dir: Path
) -> None:
    (isolated_user_dir / "key").write_bytes(b"from-file")
    assert crypto._load_or_create_key() == b"from-file"
    # Keyring became available since first run — file key is mirrored over.
    assert fake_keyring.store[(crypto._KEYRING_SERVICE, crypto._KEYRING_USER)] == "from-file"


def test_load_or_create_key_generates_and_writes_keyring(
    fake_keyring: _FakeKeyring, isolated_user_dir: Path
) -> None:
    key = crypto._load_or_create_key()
    # Stored in keyring, file fallback untouched.
    assert fake_keyring.store[(crypto._KEYRING_SERVICE, crypto._KEYRING_USER)] == key.decode(
        "ascii"
    )
    assert not (isolated_user_dir / "key").exists()


def test_load_or_create_key_falls_back_to_file_when_keyring_write_fails(
    fake_keyring: _FakeKeyring, isolated_user_dir: Path
) -> None:
    fake_keyring.raise_on_set = True
    key = crypto._load_or_create_key()
    assert (isolated_user_dir / "key").read_bytes() == key


def test_get_cipher_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    crypto.set_cipher_for_tests(None)
    calls = {"n": 0}

    def fake_load() -> bytes:
        calls["n"] += 1
        return Fernet.generate_key()

    monkeypatch.setattr(crypto, "_load_or_create_key", fake_load)
    first = crypto._get_cipher()
    second = crypto._get_cipher()
    assert first is second
    assert calls["n"] == 1
    crypto.set_cipher_for_tests(None)
