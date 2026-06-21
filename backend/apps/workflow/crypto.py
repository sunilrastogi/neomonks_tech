"""Symmetric encryption for secrets stored at rest.

Used by :class:`apps.workflow.fields.EncryptedCharField` to encrypt sensitive
connection settings (DB password, LLM API key, GitHub token) in the database.

Encrypted values are stored with a short marker prefix so we can tell them
apart from legacy plaintext and avoid double-encryption.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

# Prefix identifying an encrypted value (and the scheme version).
_MARKER = "enc$1:"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Build the Fernet cipher from CONFIG_ENCRYPTION_KEY, or derive one.

    If ``CONFIG_ENCRYPTION_KEY`` is set it must be a urlsafe-base64 Fernet key.
    Otherwise (local dev only — settings requires the explicit key when
    DEBUG is off) a stable key is derived from ``SECRET_KEY``.
    """
    key = (getattr(settings, "CONFIG_ENCRYPTION_KEY", "") or "").strip()
    if key:
        token = key.encode()
    else:
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        token = base64.urlsafe_b64encode(digest)
    return Fernet(token)


def reset_cipher_cache() -> None:
    """Clear the cached cipher (used by tests that swap keys)."""
    _fernet.cache_clear()


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(_MARKER)


def encrypt_secret(value: str) -> str:
    """Encrypt a plaintext secret. Empty/None and already-encrypted pass through."""
    if not value or is_encrypted(value):
        return value
    token = _fernet().encrypt(value.encode()).decode()
    return _MARKER + token


def decrypt_secret(value: str) -> str:
    """Decrypt a stored secret. Legacy plaintext and empty values pass through."""
    if not value or not is_encrypted(value):
        return value
    try:
        return _fernet().decrypt(value[len(_MARKER):].encode()).decode()
    except InvalidToken:
        # Wrong/rotated key or corruption — fail safe to empty rather than
        # crashing every read of the configuration.
        return ""
