-- First-deploy role bootstrap. RUN THIS ONCE, BY HAND, against the managed
-- database, connected as the owner role (POSTGRES_USER).
--
--   psql "$MIGRATIONS_DATABASE_URL" \
--        -v app_user="$APP_DB_USER" \
--        -v app_password="$APP_DB_PASSWORD" \
--        -f infra/postgres/bootstrap/10-roles.sql
--
-- Managed Postgres providers do not run docker-entrypoint-initdb.d, so this is
-- a deliberate manual step rather than an automatic one. The local development
-- container runs the very same file through infra/postgres/dev-init/, so dev
-- and production end up with identical privileges.
--
-- Two database identities (spec section 10, "least privilege"):
--   * the owner role (POSTGRES_USER) - owns the schema; Alembic connects as it
--   * APP_DB_USER                    - runtime role for the API and worker. It
--     can read and write rows but cannot create, alter or drop objects, so a
--     SQL-injection foothold in the app cannot reshape the schema.
--
-- Safe to re-run: every step is idempotent.

\set ON_ERROR_STOP on

-- users.email is CITEXT regardless of which role the app connects as.
CREATE EXTENSION IF NOT EXISTS citext;

-- psql does not interpolate :variables inside a dollar-quoted block, so the
-- values are parked in session GUCs that the block reads back out.
--
-- `\gset` captures each result instead of printing it. set_config() returns the
-- value it just set, so a plain SELECT would echo the runtime password to
-- stdout - straight into whatever deploy log is capturing this run.
SELECT set_config('checkgeo.app_user', :'app_user', false) AS _discard \gset
SELECT set_config('checkgeo.app_password', :'app_password', false) AS _discard \gset

DO $bootstrap$
DECLARE
    v_user  text := current_setting('checkgeo.app_user');
    v_pass  text := current_setting('checkgeo.app_password');
    v_db    text := current_database();
    v_owner text := current_user;
BEGIN
    IF v_user IS NULL OR v_user = '' OR v_pass IS NULL OR v_pass = '' THEN
        RAISE EXCEPTION
            'app_user and app_password must both be supplied: psql -v app_user=... -v app_password=...';
    END IF;

    -- format() with %I/%L quotes the identifier and the literal, so a role name
    -- or password containing quotes cannot break out into SQL of its own.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_user) THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', v_user, v_pass);
        RAISE NOTICE 'Created runtime role %', v_user;
    ELSE
        EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', v_user, v_pass);
        RAISE NOTICE 'Updated password for existing runtime role %', v_user;
    END IF;

    -- No object creation for anyone but the owner.
    EXECUTE 'REVOKE CREATE ON SCHEMA public FROM PUBLIC';
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', v_db);

    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', v_db, v_user);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', v_user);

    -- Existing objects (none on a fresh database, but keeps re-runs correct).
    EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', v_user);
    EXECUTE format(
        'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', v_user);

    -- Anything Alembic creates later is granted automatically.
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', v_owner, v_user);
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'GRANT USAGE, SELECT ON SEQUENCES TO %I', v_owner, v_user);
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'GRANT EXECUTE ON FUNCTIONS TO %I', v_owner, v_user);

    RAISE NOTICE 'Runtime role % has DML-only privileges on %', v_user, v_db;
END
$bootstrap$;

-- Do not leave the password sitting in the session.
SELECT set_config('checkgeo.app_password', '', false) AS _discard \gset
\unset _discard
