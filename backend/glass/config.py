from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database — default points at a local Postgres
    database_url: str = "postgresql://glass:glass_dev@127.0.0.1:5432/glass_dev"

    # Redis — default points at a local Redis
    redis_url: str = "redis://127.0.0.1:6379/0"

    # External APIs (set via env)
    anthropic_api_key: str
    deepgram_api_key: str
    exa_api_key: str

    # Auth (Clerk)
    clerk_jwks_url: str
    clerk_issuer: str

    # App
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Dev bypass — when true, glass/auth.py skips Clerk validation and
    # returns a fixed dev user. ONLY safe when the backend is bound to
    # a non-public interface (loopback or Tailscale). MUST be off in prod.
    dev_mode: bool = False


settings = Settings()  # type: ignore[call-arg]  # env-loaded
