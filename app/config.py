import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Railway provides PORT, DATABASE_URL, etc.
    port: int = int(os.getenv("PORT", "8000"))

    # Database - Railway provides DATABASE_URL (may be postgres:// or postgresql://)
    database_url: str | None = None

    # For local dev fallback
    local_db_host: str = "localhost"
    local_db_name: str = "thepractice_voice"
    local_db_user: str = "postgres"
    local_db_password: str = ""

    @property
    def effective_database_url(self) -> str:
        """Get the actual database URL to use, handling Railway's format."""
        if self.database_url:
            # Railway uses postgres://, SQLAlchemy needs postgresql://
            return self.database_url.replace("postgres://", "postgresql://", 1)
        # Local fallback
        if self.local_db_password:
            return f"postgresql://{self.local_db_user}:{self.local_db_password}@{self.local_db_host}/{self.local_db_name}"
        return f"postgresql://{self.local_db_user}@{self.local_db_host}/{self.local_db_name}"

    # Redis (optional for MVP)
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Acuity
    acuity_api_key: str
    acuity_user_id: str
    acuity_business_id: str | None = None
    acuity_api_url: str = "https://acuityscheduling.com/api/v1"

    # IntakeQ
    intakeq_api_key: str
    intakeq_api_url: str = "https://intakeq.com/api/v1"

    # Vapi
    vapi_auth_token: str

    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str | None = None

    # Human escalation
    human_transfer_number: str | None = None

    # Retention
    transcript_retention_days: int = 0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
