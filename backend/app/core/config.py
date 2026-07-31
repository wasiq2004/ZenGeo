"""Application configuration.

Every tunable comes from the environment (see `.env.example`). Nothing is
hardcoded, and the settings object is the single place secrets are read.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]

_RATE_LIMIT_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d*)\s*(second|minute|hour|day)s?\s*$")

_WINDOW_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}

# A DSN asks for TLS via asyncpg's `ssl=` or libpq's `sslmode=`; anything that
# disables or merely prefers it does not count as encrypted.
_URL_IS_TLS_RE = re.compile(
    r"[?&]ssl(?:mode)?=(?!disable|allow|prefer)(require|verify-ca|verify-full|true|on)",
    re.IGNORECASE,
)


def parse_rate_limit(spec: str) -> tuple[int, int]:
    """Turn ``"10/15minutes"`` into ``(10, 900)`` - (max requests, window seconds)."""
    match = _RATE_LIMIT_RE.match(spec)
    if not match:
        raise ValueError(
            f"Invalid rate limit {spec!r}; expected e.g. '10/minute' or '10/15minutes'"
        )
    limit, multiple, unit = match.groups()
    return int(limit), int(multiple or 1) * _WINDOW_SECONDS[unit]


def _require_expanded(value: str, name: str) -> str:
    """Fail loudly on a DSN whose ``${...}`` references were never expanded.

    The documented `.env` composes DATABASE_URL out of the other variables.
    Docker Compose expands those references when it loads the file, but a plain
    dotenv reader - pydantic-settings when the app runs outside Compose, pytest,
    a one-off `alembic` invocation - does not, and would otherwise try to
    connect to a host literally named "${POSTGRES_HOST}".
    """
    if "${" in value:
        raise ValueError(
            f"{name} still contains an unexpanded ${{...}} reference. Either run "
            f"under Docker Compose (which expands them) or write {name} out with "
            f"literal values."
        )
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # The DSN fields carry a validation_alias so DATABASE_URL maps onto
        # them. Without this, that alias becomes the *only* way to set them and
        # the field name silently stops working.
        populate_by_name=True,
    )

    # --- Core ---
    environment: Environment = "development"
    frontend_url: str = "http://localhost:8080"
    cors_origins: str = "http://localhost:8080,http://localhost:5173"
    api_prefix: str = "/api/v1"

    # --- Secrets ---
    jwt_secret_key: SecretStr = SecretStr("insecure-development-secret-change-me")
    encryption_key: SecretStr = SecretStr("")

    # --- Database (an external / managed Postgres, not a container we run) ---
    postgres_user: str = "geo_app"
    postgres_password: SecretStr = SecretStr("postgres")
    postgres_db: str = "geo_audit"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    # TLS to the managed instance. "require" encrypts but does not verify the
    # server; "verify-full" also checks the certificate chain and hostname and
    # needs POSTGRES_SSLROOTCERT. "disable" exists only for the throwaway local
    # dev container and is refused in production.
    postgres_sslmode: str = "require"
    postgres_sslrootcert: str | None = None
    app_db_user: str | None = None
    app_db_password: SecretStr | None = None

    # Fully-formed DSNs win over the components above when set. DATABASE_URL is
    # the runtime (least-privilege) connection; MIGRATIONS_DATABASE_URL is the
    # owner connection Alembic uses.
    database_url_override: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "DATABASE_URL_OVERRIDE"),
    )
    migrations_database_url_override: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MIGRATIONS_DATABASE_URL", "MIGRATION_DATABASE_URL"),
    )

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # --- Auth ---
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    login_max_attempts: int = 5
    login_lockout_seconds: int = 900

    # There is deliberately no email configuration here. This deployment sends
    # no mail at all: accounts are usable the moment they are created, and
    # password recovery is an admin action rather than a link in an inbox.
    # See app/api/routes/admin.py :: reset_user_password.

    # --- First admin ---
    first_admin_email: str = "admin@example.com"
    first_admin_password: SecretStr = SecretStr("")
    first_admin_name: str = "Platform Admin"

    # --- Audit engine ---
    reports_dir: str = "/data/reports"
    fetch_timeout_seconds: float = 15.0
    fetch_max_bytes: int = 3_000_000
    max_pages_per_audit: int = 8
    allow_private_network_fetch: bool = False
    user_agent: str = "GEO-Audit-Bot/1.0 (+https://github.com/; automated site audit)"

    # --- Share of Voice: stability safeguards, NOT usage caps ---
    sov_provider_concurrency: int = 3
    sov_request_timeout_seconds: float = 120.0
    sov_max_retries: int = 2

    # --- Rate limits ---
    rate_limit_login: str = "10/15minutes"
    rate_limit_signup: str = "5/hour"
    rate_limit_audit_start: str = "20/hour"
    rate_limit_default: str = "300/minute"

    # --- Logging ---
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard_origin(cls, value: str) -> str:
        if "*" in value:
            raise ValueError(
                "CORS_ORIGINS must be an explicit allow-list; '*' is incompatible "
                "with credentialed requests."
            )
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def _tls_query(self, driver: str) -> str:
        """TLS query string, spelled the way each driver expects.

        asyncpg takes ``ssl=``; libpq-based psycopg takes ``sslmode=``. Same
        intent, different parameter name - getting this wrong silently connects
        in cleartext, so the two are kept apart deliberately.
        """
        from urllib.parse import quote_plus

        mode = self.postgres_sslmode.strip().lower()
        if mode in {"", "disable"}:
            return ""
        key = "ssl" if driver == "asyncpg" else "sslmode"
        query = f"?{key}={quote_plus(mode)}"
        # Only libpq understands sslrootcert in the DSN; for asyncpg the CA is
        # supplied through an SSL context, so we leave the URL alone.
        if self.postgres_sslrootcert and driver != "asyncpg":
            query += f"&sslrootcert={quote_plus(self.postgres_sslrootcert)}"
        return query

    def _dsn(self, user: str, password: str, driver: str) -> str:
        from urllib.parse import quote_plus

        return (
            f"postgresql+{driver}://{quote_plus(user)}:{quote_plus(password)}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            f"{self._tls_query(driver)}"
        )

    @property
    def database_url(self) -> str:
        """Async DSN used by the API and worker (least-privilege runtime role)."""
        if self.database_url_override:
            return _require_expanded(self.database_url_override, "DATABASE_URL")
        if self.app_db_user and self.app_db_password:
            return self._dsn(
                self.app_db_user, self.app_db_password.get_secret_value(), "asyncpg"
            )
        return self._dsn(
            self.postgres_user, self.postgres_password.get_secret_value(), "asyncpg"
        )

    @property
    def migration_database_url(self) -> str:
        """Sync DSN used by Alembic - runs as the schema owner, not the app role."""
        if self.migrations_database_url_override:
            return _require_expanded(
                self.migrations_database_url_override, "MIGRATIONS_DATABASE_URL"
            )
        return self._dsn(
            self.postgres_user, self.postgres_password.get_secret_value(), "psycopg"
        )

    def validate_for_production(self) -> list[str]:
        """Return a list of unsafe-for-production configuration problems."""
        problems: list[str] = []
        if not self.is_production:
            return problems
        if "change-me" in self.jwt_secret_key.get_secret_value():
            problems.append("JWT_SECRET_KEY is still the placeholder value")
        if len(self.jwt_secret_key.get_secret_value()) < 32:
            problems.append("JWT_SECRET_KEY must be at least 32 characters")
        if not self.encryption_key.get_secret_value():
            problems.append("ENCRYPTION_KEY is required to store BYOK API keys")
        if "change-me" in self.postgres_password.get_secret_value():
            problems.append("POSTGRES_PASSWORD is still the placeholder value")
        if self.allow_private_network_fetch:
            problems.append(
                "ALLOW_PRIVATE_NETWORK_FETCH must be false in production (SSRF risk)"
            )
        if self.frontend_url.startswith("http://"):
            problems.append("FRONTEND_URL must use https in production")
        # The database is now off-box, so the hop to it crosses a network the
        # VPS does not control. Cleartext there would expose every row.
        if self.postgres_sslmode.strip().lower() in {"", "disable", "allow", "prefer"}:
            problems.append(
                "POSTGRES_SSLMODE must be 'require' or stricter in production - the "
                "managed database is reached over an untrusted network"
            )
        # No email checks: this deployment has no mail transport by design.
        # The thing that used to make that dangerous - an unreachable
        # password-reset link - no longer exists either, because recovery is an
        # admin action instead of a link.

        for name, url in (
            ("DATABASE_URL", self.database_url_override),
            ("MIGRATIONS_DATABASE_URL", self.migrations_database_url_override),
        ):
            if url and not _URL_IS_TLS_RE.search(url):
                problems.append(
                    f"{name} is set but requests no TLS; add '?ssl=require' (asyncpg) "
                    f"or '?sslmode=require' (psycopg)"
                )
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
