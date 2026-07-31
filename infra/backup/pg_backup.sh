#!/usr/bin/env bash
# Compressed pg_dump of the production database into ./backups, with rotation.
#
# Postgres runs in a container on THIS box, so there is no provider snapshot and
# no second machine holding a copy: this script IS the backup story, and nothing
# else is watching. Losing this VPS loses the application and the data together.
#
#   0 3 * * * cd /opt/checkgeo && ./infra/backup/pg_backup.sh >> /var/log/checkgeo-backup.log 2>&1
#
# Set BACKUP_REMOTE to copy each dump off this machine as it is written. A
# backup sitting on the same disk as the thing it backs up is not a backup, and
# here that is literally the same disk.
#
#   BACKUP_REMOTE=user@backup-host:/srv/checkgeo-backups
#
# A backup you have never restored is a hypothesis, not a backup - see
# pg_restore.sh and the README's restore drill.
set -euo pipefail

cd "$(dirname "$0")/../.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
# Defaults to the production stack: this script is meant to run on the VPS.
# Override for the dev stack: COMPOSE="docker compose -f docker-compose.yml"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.prod.yml}"
STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"

mkdir -p "$BACKUP_DIR"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi

DB_NAME="${POSTGRES_DB:-geo_audit}"
TARGET="${BACKUP_DIR}/${DB_NAME}-${STAMP}.sql.gz"

echo "[$(date -u +%FT%TZ)] Backing up ${DB_NAME} -> ${TARGET}"

# pg_dump runs inside the postgres container, over its local socket, as the
# owner role - the runtime role deliberately cannot read everything. Going
# through the container means no client image to keep in step with the server
# version, no credentials on the command line, and no TLS handshake to satisfy.
#
# --clean --if-exists makes the dump idempotent to restore over an existing DB.
$COMPOSE exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
  | gzip -9 > "$TARGET.partial"

# Only publish the final name once the dump completed, so a half-written file
# from an interrupted run is never mistaken for a good backup.
mv "$TARGET.partial" "$TARGET"

SIZE="$(du -h "$TARGET" | cut -f1)"
echo "[$(date -u +%FT%TZ)] Wrote ${TARGET} (${SIZE})"

# Refuse to keep an obviously empty dump around.
if [ "$(gzip -dc "$TARGET" | head -c 100 | wc -c)" -lt 50 ]; then
  echo "ERROR: dump looks empty - keeping it for inspection but treat it as failed" >&2
  exit 1
fi

echo "Pruning backups older than ${RETENTION_DAYS} days"
find "$BACKUP_DIR" -name "${DB_NAME}-*.sql.gz" -type f -mtime "+${RETENTION_DAYS}" -print -delete

# Reports live on a Docker volume, not in Postgres, so they need their own copy.
if [ "${BACKUP_REPORTS:-true}" = "true" ]; then
  REPORTS_TARGET="${BACKUP_DIR}/reports-${STAMP}.tar.gz"
  echo "[$(date -u +%FT%TZ)] Backing up stored PDF reports -> ${REPORTS_TARGET}"
  $COMPOSE exec -T backend tar -czf - -C /data reports > "$REPORTS_TARGET.partial" 2>/dev/null || true
  if [ -s "$REPORTS_TARGET.partial" ]; then
    mv "$REPORTS_TARGET.partial" "$REPORTS_TARGET"
    find "$BACKUP_DIR" -name 'reports-*.tar.gz' -type f -mtime "+${RETENTION_DAYS}" -delete
  else
    rm -f "$REPORTS_TARGET.partial"
    echo "No reports to back up yet"
  fi
fi

# --- Copy off this machine -------------------------------------------------
if [ -n "${BACKUP_REMOTE:-}" ]; then
  echo "[$(date -u +%FT%TZ)] Copying to ${BACKUP_REMOTE}"
  # Built from what is actually on disk: REPORTS_TARGET is set even when the
  # tarball turned out empty and was deleted, so testing the variable is not
  # the same as testing the file.
  COPY_FILES="$TARGET"
  if [ -n "${REPORTS_TARGET:-}" ] && [ -f "${REPORTS_TARGET}" ]; then
    COPY_FILES="$COPY_FILES $REPORTS_TARGET"
  fi
  # A non-zero exit here must fail the whole run: a backup that silently stopped
  # replicating off-box looks identical to a working one until the day you need
  # it. Cron will mail the failure.
  # shellcheck disable=SC2086  # deliberate word splitting into a file list
  if command -v rsync >/dev/null 2>&1; then
    rsync -az --partial $COPY_FILES "${BACKUP_REMOTE}/"
  else
    scp -q $COPY_FILES "${BACKUP_REMOTE}/"
  fi
  echo "[$(date -u +%FT%TZ)] Off-box copy complete"
else
  echo
  echo "WARNING: BACKUP_REMOTE is not set, so this dump exists only on this host."
  echo "Losing this VPS loses the backups with it. Set BACKUP_REMOTE to an"
  echo "rsync/scp destination on a different machine."
fi

echo "[$(date -u +%FT%TZ)] Backup complete"
