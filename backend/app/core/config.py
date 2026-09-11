"""Application settings.

One typed object, populated from environment variables (or a local `.env`) and
validated once at startup — a missing SUPABASE_URL fails loudly at boot rather
than as a confusing 500 on the first request. On Cloud Run the same variables
arrive via `--set-env-vars` / Secret Manager, so this code never knows or cares
where it runs.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    supabase_url: str  # https://<project-ref>.supabase.co
    database_url: str  # postgresql+asyncpg://... via the Supavisor pooler host
    jwt_audience: str = "authenticated"  # Supabase sets this for every signed-in user
    # Browser origins allowed to call the API (native apps are not subject to CORS).
    # Comma-separated; defaults cover Expo's web dev server.
    cors_origins: str = "http://localhost:8081,http://127.0.0.1:8081"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    # Cached so the .env file is read once per process; also a FastAPI dependency,
    # which lets tests swap it with `app.dependency_overrides`.
    return Settings()
