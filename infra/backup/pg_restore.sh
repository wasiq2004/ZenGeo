#!/usr/bin/env bash
# Restore the database from a pg_backup.sh dump.
#
#   ./infra/backup/pg_restore.sh backups/geo_audit-2026-07-30T03-00-00Z.sql.gz
#
# Practise this on a throwaway copy before you need it. The README documents
# the drill; an untested restore path is the usual reason a backup turns out
# not to be one.
set -euo pipefail

cd "$(dirname "$0")/../.."

DUMP="${1:-}"
COMPOSE="${COMPOSE:-docker compose}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"

if [ -z "$DUMP" ]; then
  echo "Usage: $0 <path-to-dump.sql.gz>" >&2
  echo >&2
  echo "Available backups:" >&2
  ls -1t ./backups/*.sql.gz 2>/dev/null | head -20 >&2 || echo "  (none found)" >&2
  exit 1
fi

if [ ! -f "$DUMP" ]; then
  echo "ERROR: $DUMP does not exist" >&2
  exit 1
fi

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
DB_NAME="${POSTGRES_DB:-geo_audit}"
RESTORE_DSN="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT:-5432}/${DB_NAME}?sslmode=${POSTGRES_SSLMODE:-require}"

# The target is a managed instance now, so name it plainly - the whole point of
# the confirmation is that you read which host you are about to overwrite.
echo "This will OVERWRITE database '${DB_NAME}' on host '${POSTGRES_HOST}'."
echo "Restoring from: $DUMP"
printf "Type 'restore' to continue: "
read -r CONFIRM
[ "$CONFIRM" = "restore" ] || { echo "Aborted."; exit 1; }

# Stop the writers first: restoring under live traffic gives a torn result.
echo "Stopping backend and worker…"
$COMPOSE stop backend worker

echo "Restoring…"
gzip -dc "$DUMP" | docker run --rm -i -e PGDSN="$RESTORE_DSN" "$PG_IMAGE" \
  sh -c 'psql -v ON_ERROR_STOP=1 "$PGDSN"'

echo "Bringing services back up…"
$COMPOSE start backend worker

echo "Applying any migrations newer than the dump…"
sleep 5
$COMPOSE exec -T backend alembic upgrade head

echo
echo "Restore complete. Verify before declaring success:"
echo "  $COMPOSE exec backend python -c \"import asyncio; print('ok')\""
echo "  curl -fsS http://localhost:8080/health/ready"
