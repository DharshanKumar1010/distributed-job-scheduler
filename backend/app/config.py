from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    WORKER_CONCURRENCY: int
    WORKER_POLL_INTERVAL_SECONDS: int
    HEARTBEAT_INTERVAL_SECONDS: int
    REAPER_INTERVAL_SECONDS: int
    ANTHROPIC_API_KEY: str = ""


settings = Settings()
