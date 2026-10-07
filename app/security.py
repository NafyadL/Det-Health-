"""Password-derived encryption for local health records."""

import base64
import hmac
import re

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

PASSWORD_VERIFIER = b"Det(Health) local account verifier v1"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def valid_username(username: str) -> bool:
    return USERNAME_PATTERN.fullmatch(username) is not None


def derive_key(password: str, salt: bytes) -> bytes:
    raw_key = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(
        password.encode("utf-8")
    )
    return base64.urlsafe_b64encode(raw_key)


def encrypt(key: bytes, plaintext: bytes) -> bytes:
    return Fernet(key).encrypt(plaintext)


def decrypt(key: bytes, ciphertext: bytes) -> bytes:
    return Fernet(key).decrypt(ciphertext)


def verifier_matches(key: bytes, verifier: bytes) -> bool:
    try:
        decrypted = decrypt(key, verifier)
    except InvalidToken:
        return False
    return hmac.compare_digest(decrypted, PASSWORD_VERIFIER)
