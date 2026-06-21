"""Custom model fields for the workflow app."""
from __future__ import annotations

from django.db import models

from apps.workflow.crypto import decrypt_secret, encrypt_secret


class EncryptedCharField(models.CharField):
    """A CharField that transparently encrypts its value at rest.

    Values are encrypted (Fernet) before being written to the database and
    decrypted when loaded, so model and serializer code work with plaintext.
    Rows written before encryption was introduced are stored as plaintext and
    are returned unchanged until the next save re-encrypts them.

    Note: the encrypted ciphertext is longer than the plaintext, so give these
    fields a generous ``max_length`` (e.g. 1024).
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_secret(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        return encrypt_secret(value)
