"""Helpers to encrypt/decrypt sensitive values (e.g. router passwords).

The key comes from the FERNET_KEY setting. Generate one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

and put it in your .env as FERNET_KEY=...
"""

from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken


class CryptoNotConfigured(RuntimeError):
    pass


def _fernet():
    key = getattr(settings, "FERNET_KEY", "") or ""
    if not key:
        raise CryptoNotConfigured(
            "FERNET_KEY no está configurada. Genera una y agrégala al .env."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        plaintext = ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
