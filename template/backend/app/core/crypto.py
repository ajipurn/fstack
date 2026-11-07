"""Provider credentials at rest: AES-256-GCM, AAD bound to the owning row.

Blob layout: urlsafe-base64(b"v1" + nonce(12) + ciphertext+tag). Binding the AAD
to the provider id means a ciphertext copied onto another row will not decrypt.
"""

import base64
import binascii
import contextlib
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import BACKEND_ROOT, get_settings

VERSION = b"v1"
LOCAL_KEY = BACKEND_ROOT / ".data" / "encryption.key"


class SecretError(Exception):
    pass


def parse_key(raw: str) -> bytes:
    raw = raw.strip()
    candidates: list[bytes] = []
    with contextlib.suppress(ValueError):
        candidates.append(bytes.fromhex(raw))
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        with contextlib.suppress(binascii.Error, ValueError):
            candidates.append(decoder(raw + "=" * (-len(raw) % 4)))
    for key in candidates:
        if len(key) == 32:
            return key
    raise SecretError("APP_ENCRYPTION_KEY must decode to exactly 32 bytes.")


def load_key() -> bytes:
    settings = get_settings()
    if settings.encryption_key.strip():
        return parse_key(settings.encryption_key)
    if settings.environment == "production":
        raise SecretError("APP_ENCRYPTION_KEY is required in production.")
    # Development fallback: one key per checkout, never committed.
    if not LOCAL_KEY.exists():
        LOCAL_KEY.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_KEY.write_text(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
        LOCAL_KEY.chmod(0o600)
    return parse_key(LOCAL_KEY.read_text())


def encrypt(plaintext: str, owner_id: str) -> str:
    nonce = os.urandom(12)
    token = AESGCM(load_key()).encrypt(nonce, plaintext.encode(), owner_id.encode())
    return base64.urlsafe_b64encode(VERSION + nonce + token).decode()


def decrypt(token: str, owner_id: str) -> str:
    try:
        data = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        if not data.startswith(VERSION) or len(data) < 14:
            raise ValueError("bad blob")
        nonce, ciphertext = data[2:14], data[14:]
        return AESGCM(load_key()).decrypt(nonce, ciphertext, owner_id.encode()).decode()
    except (InvalidTag, ValueError, TypeError) as exc:
        raise SecretError(
            "Stored credentials cannot be decrypted. Restore APP_ENCRYPTION_KEY."
        ) from exc


def hint(value: str) -> str:
    """'sk-proj-abc…wxyz' → 'sk-••••wxyz'. Never reveals more than 7 chars."""
    text = value.strip()
    return "••••" if len(text) <= 10 else f"{text[:3]}••••{text[-4:]}"
