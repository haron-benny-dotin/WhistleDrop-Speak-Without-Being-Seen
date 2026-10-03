import logging
import os
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("whistledrop")

DEV_SECRET = "dev-only-secret-change-me"


@dataclass(frozen=True)
class Settings:
    database_path: str
    case_code_secret: bytes
    session_ttl_minutes: int
    bootstrap_username: Optional[str] = None
    bootstrap_password: Optional[str] = None


def load_settings() -> Settings:
    secret = os.environ.get("WD_CASE_SECRET", "")
    if not secret:
        log.warning("WD_CASE_SECRET is not set - using an insecure development secret.")
        secret = DEV_SECRET

    return Settings(
        database_path=os.environ.get("WD_DB_PATH", "whistledrop.db"),
        case_code_secret=secret.encode("utf-8"),
        session_ttl_minutes=int(os.environ.get("WD_SESSION_TTL_MINUTES", "120")),
        bootstrap_username=os.environ.get("WD_BOOTSTRAP_MOD_USER") or None,
        bootstrap_password=os.environ.get("WD_BOOTSTRAP_MOD_PASS") or None,
    )
