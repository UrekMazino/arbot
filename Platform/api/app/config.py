import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OKXStatBot V2 API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    api_prefix: str = "/api/v2"

    database_url: str = "postgresql+psycopg2://okxbot:okxbot@localhost:5432/okxbot_v2"
    redis_url: str = "redis://localhost:6379/0"

    access_token_secret: str = "change-me-access"
    access_token_minutes: int = 15
    refresh_token_secret: str = "change-me-refresh"
    refresh_token_days: int = 14
    jwt_algorithm: str = "HS256"

    bootstrap_admin_email: str = "admin@okxstatbot.local"
    bootstrap_admin_password: str = "ChangeMeNow123!"

    event_batch_max: int = 200
    event_spool_dir: str = os.path.join("Execution", "state", "event_spool")
    event_ingest_key: str = ""
    event_allow_unauthenticated: bool = True
    event_publish_realtime: bool = True


settings = Settings()
