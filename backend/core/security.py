"""
Fernet-based symmetric encryption for connector credentials stored in the DB.
Credentials are always encrypted at rest and decrypted only in memory.
"""
import json
from cryptography.fernet import Fernet, InvalidToken

from .config import settings


def _get_fernet() -> Fernet:
    key = settings.fernet_key
    if not key:
        # Dev fallback: generate a consistent key from secret_key (NOT for production)
        import base64
        import hashlib
        raw = hashlib.sha256(settings.secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(raw).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_credentials(credentials: dict) -> str:
    """Encrypt a credentials dict to a Fernet token string."""
    f = _get_fernet()
    plaintext = json.dumps(credentials).encode()
    return f.encrypt(plaintext).decode()


def decrypt_credentials(token: str) -> dict:
    """Decrypt a Fernet token string back to a credentials dict."""
    f = _get_fernet()
    try:
        plaintext = f.decrypt(token.encode())
        return json.loads(plaintext)
    except (InvalidToken, Exception) as exc:
        raise ValueError(f"Failed to decrypt credentials: {exc}") from exc
