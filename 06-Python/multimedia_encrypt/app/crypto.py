import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12       # GCM standard: 96-bit nonce
KEY_SIZE   = 32       # AES-256: 32 bytes

# Additional authenticated data — binds ciphertext to this application context
# Prevents cross-context reuse of ciphertext blobs
AAD = b"multimedia_encrypt_v1"


def generate_key() -> bytes:
    """Return 32 cryptographically random bytes (AES-256 key)."""
    return os.urandom(KEY_SIZE)


def encrypt_chunk(key: bytes, plaintext: bytes) -> bytes:
    """
    Encrypt plaintext under key using AES-256-GCM.

    On-disk format: [ 12-byte nonce ][ ciphertext + 16-byte GCM tag ]

    A fresh nonce is generated per call, making nonce reuse statistically
    impossible even for files with thousands of chunks.
    """
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, AAD)
    return nonce + ciphertext


def decrypt_chunk(key: bytes, blob: bytes) -> bytes:
    """
    Decrypt a blob produced by encrypt_chunk.

    Raises:
        cryptography.exceptions.InvalidTag: if ciphertext or tag is tampered.
    """
    nonce = blob[:NONCE_SIZE]
    ciphertext = blob[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, AAD)
