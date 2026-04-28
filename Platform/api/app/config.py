import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OKXStatBot V2 API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    api_prefix: str = "/api/v2"
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"

    database_url: str = "postgresql+psycopg2://okxbot:okxbot@localhost:5432/okxbot_v2"
    redis_url: str = "redis://localhost:6379/0"

    access_token_secret: str = "change-me-access"
    access_token_minutes: int = 15
    refresh_token_secret: str = "change-me-refresh"
    refresh_token_days: int = 14
    password_reset_minutes: int = 30
    password_reset_link_base: str = "http://127.0.0.1:3000/reset-password"
    password_reset_return_token_in_response: bool = False
    email_provider: str = "resend"
    email_from: str = ""
    resend_api_key: str = ""
    resend_api_base: str = "https://api.resend.com"
    jwt_algorithm: str = "HS256"

    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    event_batch_max: int = 200
    event_spool_dir: str = os.path.join("Execution", "state", "event_spool")
    event_ingest_key: str = ""
    event_allow_unauthenticated: bool = True
    event_publish_realtime: bool = True
    equity_snapshot_min_change_usdt: float = 0.01
    equity_snapshot_keepalive_seconds: int = 300

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in str(self.cors_origins or "").split(",") if item.strip()]

    def validate_runtime_safety(self) -> None:
        if str(self.app_env or "").strip().lower() != "production":
            return

        errors: list[str] = []
        if not str(self.access_token_secret or "").strip() or self.access_token_secret == "change-me-access":
            errors.append("ACCESS_TOKEN_SECRET must be set")
        if not str(self.refresh_token_secret or "").strip() or self.refresh_token_secret == "change-me-refresh":
            errors.append("REFRESH_TOKEN_SECRET must be set")
        if self.event_allow_unauthenticated:
            errors.append("EVENT_ALLOW_UNAUTHENTICATED must be false")
        if not str(self.event_ingest_key or "").strip():
            errors.append("EVENT_INGEST_KEY must be set")

        if errors:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


settings = Settings()
