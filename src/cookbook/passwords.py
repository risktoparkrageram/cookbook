import base64
import hashlib
import hmac
import secrets

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024
SALT_BYTES = 16
KEY_BYTES = 32


def hash_password(password: str) -> str:
    """
    Hash a password with scrypt and a random salt.

    The result is "scrypt$n$r$p$salt$key" with base64 salt and key, so the cost
    parameters can change later without invalidating stored hashes.
    """
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
        dklen=KEY_BYTES,
    )
    encoded_salt = base64.b64encode(salt).decode()
    encoded_key = base64.b64encode(key).decode()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${encoded_salt}${encoded_key}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash in constant time; a malformed hash never matches."""
    try:
        scheme, n, r, p, encoded_salt, encoded_key = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(encoded_key, validate=True)
        key = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(encoded_salt, validate=True),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=SCRYPT_MAXMEM,
            dklen=len(expected),
        )
    except ValueError:
        return False
    return hmac.compare_digest(key, expected)
