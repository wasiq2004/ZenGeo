"""Password hashing, tokens, encryption and input validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.security import (
    constant_time_equals,
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.schemas.auth import LoginRequest, SignupRequest
from app.schemas.business import normalise_url


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", hashed)

    def test_wrong_password_is_rejected(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert not verify_password("wrong-horse-battery-staple", hashed)

    def test_uses_argon2id(self):
        assert hash_password("some-password-here").startswith("$argon2id$")

    def test_hashes_are_salted(self):
        # Identical passwords must not produce identical hashes.
        assert hash_password("same-password-x") != hash_password("same-password-x")

    def test_malformed_hash_is_rejected_rather_than_raising(self):
        assert not verify_password("anything", "not-a-real-hash")

    def test_empty_password_does_not_verify(self):
        assert not verify_password("", hash_password("a-real-password"))


class TestTokens:
    def test_access_token_roundtrip(self):
        token, expires_in = create_access_token(
            user_id="00000000-0000-0000-0000-000000000001",
            role="user",
            email_verified=True,
        )
        payload = decode_access_token(token)

        assert payload["sub"] == "00000000-0000-0000-0000-000000000001"
        assert payload["role"] == "user"
        assert payload["type"] == "access"
        assert expires_in > 0

    def test_tampered_token_is_rejected(self):
        import jwt

        token, _ = create_access_token(user_id="x", role="user", email_verified=True)
        tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")

        with pytest.raises(jwt.PyJWTError):
            decode_access_token(tampered)

    def test_a_token_signed_with_another_key_is_rejected(self):
        import jwt

        # Full-length key so the forgery is realistic rather than being caught
        # incidentally by a key-length check.
        forged = jwt.encode(
            {"sub": "x", "type": "access", "exp": 9999999999},
            "an-attackers-own-signing-key-of-realistic-length-0123456789",
        )
        with pytest.raises(jwt.PyJWTError):
            decode_access_token(forged)

    def test_algorithm_is_pinned_against_none(self):
        """An unsigned token must never be accepted."""
        import jwt

        unsigned = jwt.encode({"sub": "x", "type": "access", "exp": 9999999999}, key="", algorithm="none")
        with pytest.raises(jwt.PyJWTError):
            decode_access_token(unsigned)

    def test_opaque_tokens_are_unique_and_long(self):
        tokens = {generate_opaque_token() for _ in range(100)}
        assert len(tokens) == 100
        assert all(len(token) >= 32 for token in tokens)

    def test_token_hash_is_stable_and_one_way(self):
        token = generate_opaque_token()
        assert hash_token(token) == hash_token(token)
        assert token not in hash_token(token)
        assert len(hash_token(token)) == 64  # sha256 hex

    def test_constant_time_compare(self):
        assert constant_time_equals("abc", "abc")
        assert not constant_time_equals("abc", "abd")
        assert not constant_time_equals("abc", "abcd")


class TestEncryption:
    def test_roundtrip(self):
        secret = "sk-ant-api03-example-key-value"
        assert decrypt_secret(encrypt_secret(secret)) == secret

    def test_ciphertext_does_not_contain_the_plaintext(self):
        secret = "sk-proj-SUPERSECRETVALUE"
        assert secret.encode() not in encrypt_secret(secret)

    def test_encryption_is_non_deterministic(self):
        # Fernet includes a random IV, so identical inputs differ on the wire.
        secret = "sk-same-secret-twice"
        assert encrypt_secret(secret) != encrypt_secret(secret)

    def test_tampered_ciphertext_fails_to_decrypt(self):
        from app.core.crypto import EncryptionError

        blob = bytearray(encrypt_secret("sk-tamper-me"))
        blob[-1] ^= 0xFF

        with pytest.raises(EncryptionError):
            decrypt_secret(bytes(blob))

    def test_refuses_to_encrypt_nothing(self):
        from app.core.crypto import EncryptionError

        with pytest.raises(EncryptionError):
            encrypt_secret("")

    @pytest.mark.parametrize(
        ("secret", "expected"),
        [
            ("sk-proj-abcdefghijklmnop", "sk-proj...mnop"),
            ("sk-ant-api03-xxxxxxxxxxxxwxyz", "sk-ant-...wxyz"),
            ("short", "•••••"),
        ],
    )
    def test_preview_reveals_only_the_ends(self, secret: str, expected: str):
        preview = mask_secret(secret)
        assert preview == expected
        # The middle - the part that makes the key usable - must not survive.
        if len(secret) > 14:
            assert secret[8:-4] not in preview


class TestInputValidation:
    def test_signup_rejects_unknown_fields(self):
        """extra=forbid is what stops a role being smuggled in at signup."""
        with pytest.raises(ValidationError):
            SignupRequest(
                email="a@example.com",
                password="a-long-enough-password",
                role="admin",  # type: ignore[call-arg]
            )

    def test_signup_rejects_a_short_password(self):
        with pytest.raises(ValidationError):
            SignupRequest(email="a@example.com", password="short")

    def test_signup_rejects_a_common_password(self):
        with pytest.raises(ValidationError):
            SignupRequest(email="a@example.com", password="password1234")

    def test_signup_rejects_a_repetitive_password(self):
        with pytest.raises(ValidationError):
            SignupRequest(email="a@example.com", password="aaaaaaaaaaaaaa")

    def test_signup_rejects_a_malformed_email(self):
        with pytest.raises(ValidationError):
            SignupRequest(email="not-an-email", password="a-long-enough-password")

    def test_login_accepts_a_short_password(self):
        """Login must not apply the strength policy - existing users may have
        older passwords, and rejecting them here would leak policy details."""
        assert LoginRequest(email="a@example.com", password="x").password == "x"


class TestUrlNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("example.com", "https://example.com"),
            ("https://example.com", "https://example.com"),
            ("http://example.com/path", "http://example.com/path"),
            ("  https://example.com  ", "https://example.com"),
            ("https://example.com/page#section", "https://example.com/page"),
        ],
    )
    def test_normalises_what_a_person_would_type(self, raw: str, expected: str):
        assert normalise_url(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", "ftp://example.com", "not a url", "https://"])
    def test_rejects_unusable_input(self, raw: str):
        with pytest.raises(ValueError):
            normalise_url(raw)
