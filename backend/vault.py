import os
import base64
from cryptography.fernet import Fernet

# Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
_raw = os.getenv("VAULT_KEY", "")

def _fernet() -> Fernet:
    if not _raw:
        raise RuntimeError("VAULT_KEY env var not set")
    key = _raw.encode() if len(_raw) == 44 else base64.urlsafe_b64encode(_raw.encode()[:32].ljust(32, b"="))
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
