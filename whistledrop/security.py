import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    return dt.strftime(TIME_FORMAT)


def now_iso() -> str:
    return to_iso(utc_now())


def iso_after(minutes: int) -> str:
    return to_iso(utc_now() + timedelta(minutes=minutes))


# case codes look like WD-XXXX-XXXX-XXXX
# no 0/O/1/I/L so they are easier to read and type
CASE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CASE_LENGTH = 12
CASE_PREFIX = "WD"


def generate_case_code() -> str:
    chars = "".join(secrets.choice(CASE_ALPHABET) for _ in range(CASE_LENGTH))
    return f"{CASE_PREFIX}-{chars[0:4]}-{chars[4:8]}-{chars[8:12]}"


def normalize_case_code(raw: str) -> Optional[str]:
    cleaned = "".join(ch for ch in raw.upper() if ch.isalnum())
    if cleaned.startswith(CASE_PREFIX) and len(cleaned) == CASE_LENGTH + len(CASE_PREFIX):
        cleaned = cleaned[len(CASE_PREFIX):]
    if len(cleaned) != CASE_LENGTH or any(ch not in CASE_ALPHABET for ch in cleaned):
        return None
    return cleaned


def hash_case_code(normalized_code: str, secret: bytes) -> str:
    # HMAC with a server secret, so someone with only the db can't test guessed codes
    return hmac.new(secret, normalized_code.encode("ascii"), hashlib.sha256).hexdigest()


_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt_b64),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_dummy_hash: Optional[str] = None


def burn_password_check(password: str) -> None:
    # run a fake check for unknown usernames so the response time is the same
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password")
    verify_password(password, _dummy_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
