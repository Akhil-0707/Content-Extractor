from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://training:change-me@localhost:5432/training"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "documents"

    jwt_secret: str = "dev-only-secret"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    llm_base_url: str = "http://localhost:8080/v1"
    llm_model: str = ""
    whisper_model: str = "distil-large-v3"
    embedding_model: str = "BAAI/bge-m3"
    searxng_url: str = "http://localhost:8888"

    max_upload_bytes: int = 3 * 1024**3


settings = Settings()
