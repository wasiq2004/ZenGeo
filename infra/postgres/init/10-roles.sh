#!/bin/bash
# Runs in BOTH stacks - development and production both run Postgres in a
# container, and both mount this directory into the image's init hook.
#
# Postgres runs it once, as the superuser, the first time the data volume is
# created. It just feeds the shared bootstrap script to psql, so the API and
# worker get their least-privilege runtime role automatically instead of
# needing the manual first-deploy step a managed provider would have required.
#
# Because it only fires on an empty data directory, editing 10-roles.sql has no
# effect on an existing database - apply such changes by hand:
#   docker compose -f docker-compose.prod.yml exec postgres \
#     psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /bootstrap/10-roles.sql
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
