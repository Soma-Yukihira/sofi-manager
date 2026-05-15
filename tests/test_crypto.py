"""Unit tests for crypto.py — uses an injected Fernet so the OS keyring
and any fallback file on the developer's machine are never touched."""

from __future__ import annotations

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
