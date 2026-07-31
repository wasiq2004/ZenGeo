#!/bin/bash
# DEVELOPMENT ONLY.
#
# The throwaway Postgres container in docker-compose.override.yml runs this once,
# as the superuser, the first time its data volume is created. It just feeds the
# shared bootstrap script to psql - the same file an operator runs by hand
# against the managed database on first deploy - so local privileges match
# production instead of drifting from it.
#
# Managed providers have no equivalent hook, which is why the real thing is a
# documented manual step (see the README, "First deploy").
set -euo pipefail

if [ -z "${APP_DB_USER:-}" ] || [ -z "${APP_DB_PASSWORD:-}" ]; then
  echo "[init] APP_DB_USER/APP_DB_PASSWORD not set - skipping runtime role creation."
  echo "[init] The application will fall back to connecting as ${POSTGRES_USER}."
  exit 0
fi

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v app_user="$APP_DB_USER" \
     -v app_password="$APP_DB_PASSWORD" \
     -f /bootstrap/10-roles.sql
