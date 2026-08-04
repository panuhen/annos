from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All values overridable via ANNOS_* env vars."""

    model_config = SettingsConfigDict(env_prefix="ANNOS_", env_file=".env", extra="ignore")

    # Runtime connection: the annos_api role, which has no access to Better
    # Auth's tables. See db/init/01-roles.sql.
    database_url: str = "postgresql+asyncpg://annos_api:annos@localhost:5433/annos"

    # Migrations need the owner role, since annos_api cannot create tables.
    # Falls back to database_url when unset (fine for a single-role dev setup).
    migration_database_url: str | None = None

    @property
    def alembic_url(self) -> str:
        return self.migration_database_url or self.database_url

    # Better Auth lives in the Next.js app and is the OAuth 2.1 authorization
    # server. The API is only a resource server: it validates bearer tokens
    # against these endpoints and never touches the auth tables directly.
    auth_base_url: str = "http://localhost:3000/api/auth"

    # Phase 0 only. When set, resolve_caller() skips token validation and
    # returns this subject. Must be unset in production — see identity.py.
    dev_subject: str | None = None

    # Seconds to cache a successful userinfo lookup, keyed by token. Keeps the
    # Next.js app off the hot path for every MCP tool call.
    token_cache_ttl_seconds: int = 60

    log_level: str = "INFO"


settings = Settings()
