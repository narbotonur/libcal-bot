from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    first_name: str
    last_name: str
    email: str
    id_card: str
    department: str
    purpose: str
    headless: bool
    base_url: str
    timeout_ms: int


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config() -> AppConfig:
    return AppConfig(
        first_name=os.getenv("USER_FIRST_NAME", "").strip(),
        last_name=os.getenv("USER_LAST_NAME", "").strip(),
        email=os.getenv("USER_EMAIL", "").strip(),
        id_card=os.getenv("USER_ID_CARD", "").strip(),
        department=os.getenv("USER_DEPARTMENT", "").strip(),
        purpose=os.getenv("USER_PURPOSE", "").strip(),
        headless=_to_bool(os.getenv("HEADLESS", "false"), False),
        base_url=os.getenv(
            "BASE_URL",
            "https://nu-kz.libcal.com/reserve/individuals"
        ).strip(),
        timeout_ms=int(os.getenv("TIMEOUT_MS", "20000")),
    )