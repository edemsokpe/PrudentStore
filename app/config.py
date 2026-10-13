import logging

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_MINUTES: int = 60 * 24 * 7
    R2_ACCOUNT_ID: str
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_BUCKET: str
    R2_PUBLIC_URL: str
    PAYSTACK_SECRET_KEY: str = ""
    FRONTEND_URL: str = "http://127.0.0.1:8000"
    ENV: str = "development"  # set to "production" on the live site
    MAX_BODY_MB: int = 30
    DEFAULT_DELIVERY_FEE: float = 45.0
    ORDER_PAYMENT_TIMEOUT_MINUTES: int = 60
    EXPIRY_CHECK_SECONDS: int = 300
    BREVO_API_KEY: str = ""
    MAIL_FROM_EMAIL: str = ""
    MAIL_FROM_NAME: str = "PRUDENT TECH"
    ARKESEL_API_KEY: str = ""
    SMS_SENDER_ID: str = "PRUDENTTECH"
    ADMIN_NOTIFY_EMAIL: str = ""
    ADMIN_NOTIFY_PHONE: str = ""
    CORS_ORIGINS: str = "*"


    @field_validator("DATABASE_URL")
    @classmethod
    def fix_db_url(cls, v: str) -> str:
        """Neon and Render hand out postgres:// or postgresql:// links; SQLAlchemy needs the driver name."""
        v = v.strip()
        for old in ("postgres://", "postgresql://"):
            if v.startswith(old):
                return "postgresql+psycopg2://" + v[len(old):]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENV.strip().lower() == "production"


settings = Settings()


def check_production_settings() -> None:
    """Refuse to start the live site with unsafe settings."""
    if not settings.is_production:
        return
    problems = []
    if len(settings.SECRET_KEY) < 32 or "change-this" in settings.SECRET_KEY.lower():
        problems.append("SECRET_KEY must be a long random value (at least 32 characters)")
    if "127.0.0.1" in settings.FRONTEND_URL or "localhost" in settings.FRONTEND_URL:
        problems.append("FRONTEND_URL must be your live site address, for example https://your-shop.onrender.com")
    if problems:
        raise RuntimeError("Unsafe production settings:\n - " + "\n - ".join(problems))
    log = logging.getLogger("config")
    if settings.PAYSTACK_SECRET_KEY.startswith("sk_test"):
        log.warning("PAYSTACK_SECRET_KEY is a TEST key: customers cannot really pay yet")
    if not settings.PAYSTACK_SECRET_KEY:
        log.warning("PAYSTACK_SECRET_KEY is empty: only pay on delivery is available")
