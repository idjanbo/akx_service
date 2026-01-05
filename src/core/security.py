"""AKX Crypto Payment Gateway - Security utilities for AES encryption."""

import base64
import secrets
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    pass


class AESCipher:
    """AES-256-GCM encryption for sensitive data like private keys.

    Usage:
        cipher = AESCipher(key_base64)
        encrypted = cipher.encrypt(plaintext)
        decrypted = cipher.decrypt(encrypted)

    The encrypted output format: base64(nonce + ciphertext + tag)
    - nonce: 12 bytes
    - ciphertext: variable length
    - tag: 16 bytes (appended by AESGCM)
    """

    NONCE_SIZE = 12  # 96 bits recommended for GCM

    def __init__(self, key_base64: str) -> None:
        """Initialize with base64-encoded 32-byte key.

        Args:
            key_base64: Base64-encoded 32-byte (256-bit) key
        """
        key = base64.b64decode(key_base64)
        if len(key) != 32:
            raise ValueError("AES key must be exactly 32 bytes (256 bits)")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string to base64-encoded ciphertext.

        Args:
            plaintext: The string to encrypt (e.g., private key)

        Returns:
            Base64-encoded string containing nonce + ciphertext + tag
        """
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        # Output: nonce (12) + ciphertext + tag (16)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, encrypted_b64: str) -> str:
        """Decrypt base64-encoded ciphertext to plaintext string.

        Args:
            encrypted_b64: Base64-encoded string from encrypt()

        Returns:
            Original plaintext string

        Raises:
            cryptography.exceptions.InvalidTag: If tampering detected
        """
        data = base64.b64decode(encrypted_b64)
        nonce = data[: self.NONCE_SIZE]
        ciphertext = data[self.NONCE_SIZE :]
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")


def generate_aes_key() -> str:
    """Generate a new random AES-256 key as base64 string.

    Use this to generate the AES_ENCRYPTION_KEY environment variable value.

    Returns:
        Base64-encoded 32-byte key
    """
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


# Singleton cipher instance (initialized on first use)
_cipher: AESCipher | None = None


def get_cipher() -> AESCipher:
    """Get the singleton AES cipher instance.

    Initializes from settings on first call.
    """
    global _cipher
    if _cipher is None:
        from src.core.config import get_settings

        _cipher = AESCipher(get_settings().aes_encryption_key)
    return _cipher


def encrypt_private_key(private_key: str) -> str:
    """Encrypt a private key for database storage.

    Args:
        private_key: Raw private key string

    Returns:
        Encrypted, base64-encoded string safe for database storage
    """
    return get_cipher().encrypt(private_key)


def decrypt_private_key(encrypted: str) -> str:
    """Decrypt a private key from database storage.

    Args:
        encrypted: Encrypted private key from database

    Returns:
        Raw private key string

    Warning:
        Clear the returned value from memory after use!
    """
    return get_cipher().decrypt(encrypted)


# Generic aliases for sensitive data encryption
encrypt_sensitive_data = encrypt_private_key
decrypt_sensitive_data = decrypt_private_key
