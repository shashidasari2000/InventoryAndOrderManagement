from cryptography.fernet import Fernet
from app.config import get_settings
import base64

settings = get_settings()


def _get_cipher() -> Fernet:
    key = settings.ENCRYPTION_KEY.encode()
    # Ensure key is valid base64 Fernet key
    try:
        return Fernet(key)
    except Exception:
        # Generate a valid key from the provided secret using base64
        padded = base64.urlsafe_b64encode(key[:32].ljust(32, b"0"))
        return Fernet(padded)


def encrypt_message(plaintext: str) -> str:
    cipher = _get_cipher()
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_message(ciphertext: str) -> str:
    cipher = _get_cipher()
    return cipher.decrypt(ciphertext.encode()).decode()
