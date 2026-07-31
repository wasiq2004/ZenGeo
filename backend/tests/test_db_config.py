"""Database connection configuration.

The database is an external managed instance, so the DSN the app builds is the
only thing standing between "encrypted hop across someone else's network" and
"cleartext hop across someone else's network". These check that the TLS
parameter is spelled correctly per driver, that production refuses a weak
setting, and that an unexpanded `${...}` fails loudly instead of being dialled.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "postgres_host": "db.provider.example",
        "postgres_port": 5432,
        "postgres_db": "geo_audit",
        "postgres_user": "geo_app",
        "postgres_password": "owner-secret",
        "app_db_user": "geo_runtime",
        "app_db_password": "runtime-secret",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestDsnConstruction:
    def test_runtime_dsn_uses_the_least_privilege_role(self):
        dsn = make_settings().database_url
        assert dsn.startswith("postgresql+asyncpg://geo_runtime:")
        assert "geo_app" not in dsn

    def test_migration_dsn_uses_the_owner_role(self):
        dsn = make_settings().migration_database_url
        assert dsn.startswith("postgresql+psycopg://geo_app:")
        assert "geo_runtime" not in dsn

    def test_asyncpg_and_psycopg_spell_tls_differently(self):
        settings = make_settings(postgres_sslmode="require")
        # asyncpg takes `ssl=`; libpq-based psycopg takes `sslmode=`. Swapping
        # them is silently ignored by the driver, so the two must not converge.
        assert settings.database_url.endswith("?ssl=require")
        assert settings.migration_database_url.endswith("?sslmode=require")

    def test_disable_emits_no_tls_parameter_at_all(self):
        # The local dev container serves plain TCP; an `ssl=disable` in the URL
        # would be a parameter asyncpg has to interpret rather than an absence.
        settings = make_settings(postgres_sslmode="disable")
        assert "ssl" not in settings.database_url
        assert "sslmode" not in settings.migration_database_url

    def test_root_certificate_is_only_added_for_libpq(self):
        settings = make_settings(
            postgres_sslmode="verify-full", postgres_sslrootcert="/etc/ssl/ca.crt"
        )
        assert "sslrootcert=%2Fetc%2Fssl%2Fca.crt" in settings.migration_database_url
        # asyncpg gets its CA through an SSL context, not the URL.
        assert "sslrootcert" not in settings.database_url

    def test_special_characters_in_the_password_are_escaped(self):
        settings = make_settings(app_db_password="p@ss:w/rd?#")
        dsn = settings.database_url
        assert "p%40ss%3Aw%2Frd%3F%23" in dsn
        # The raw form would terminate the userinfo early and point the app at
        # a different host entirely.
        assert "@db.provider.example:5432" in dsn

    def test_an_explicit_dsn_overrides_the_components(self):
        settings = make_settings(
            database_url_override="postgresql+asyncpg://u:p@elsewhere:5432/other?ssl=require"
        )
        assert settings.database_url == "postgresql+asyncpg://u:p@elsewhere:5432/other?ssl=require"


class TestUnexpandedReferences:
    @pytest.mark.parametrize(
        "field, prop",
        [
            ("database_url_override", "database_url"),
            ("migrations_database_url_override", "migration_database_url"),
        ],
    )
    def test_an_unexpanded_variable_is_refused(self, field: str, prop: str):
        # Compose expands ${...} when it loads .env; a plain dotenv reader does
        # not, and would otherwise dial a host literally named "${POSTGRES_HOST}".
        settings = make_settings(
            **{field: "postgresql+asyncpg://u:p@${POSTGRES_HOST}:5432/db?ssl=require"}
        )
        with pytest.raises(ValueError, match="unexpanded"):
            getattr(settings, prop)


class TestProductionGuards:
    @pytest.mark.parametrize("mode", ["disable", "allow", "prefer", ""])
    def test_production_refuses_a_weak_ssl_mode(self, mode: str):
        problems = make_settings(
            environment="production", postgres_sslmode=mode
        ).validate_for_production()
        assert any("POSTGRES_SSLMODE" in problem for problem in problems)

    @pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
    def test_production_accepts_real_tls(self, mode: str):
        problems = make_settings(
            environment="production", postgres_sslmode=mode
        ).validate_for_production()
        assert not any("POSTGRES_SSLMODE" in problem for problem in problems)

    def test_production_refuses_an_explicit_dsn_without_tls(self):
        problems = make_settings(
            environment="production",
            postgres_sslmode="require",
            database_url_override="postgresql+asyncpg://u:p@host:5432/db",
        ).validate_for_production()
        assert any("DATABASE_URL" in problem and "TLS" in problem for problem in problems)

    def test_production_refuses_a_dsn_that_merely_prefers_tls(self):
        problems = make_settings(
            environment="production",
            postgres_sslmode="require",
            migrations_database_url_override=(
                "postgresql+psycopg://u:p@host:5432/db?sslmode=prefer"
            ),
        ).validate_for_production()
        assert any("MIGRATIONS_DATABASE_URL" in problem for problem in problems)

    def test_development_is_left_alone(self):
        # Weak TLS locally is fine and must not block the dev stack booting.
        assert make_settings(environment="development", postgres_sslmode="disable") \
            .validate_for_production() == []
