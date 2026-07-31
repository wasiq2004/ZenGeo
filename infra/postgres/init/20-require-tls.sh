#!/bin/sh
# Make TLS mandatory for TCP connections to this server.
#
# Runs only when REQUIRE_TLS=true, which the production stack sets and the
# development stack does not: the dev Postgres serves plain TCP and its app
# connects with POSTGRES_SSLMODE=disable, so enforcing this there would lock the
# backend out of its own database.
#
# Without this, `ssl=on` only means TLS is *available*. The stock pg_hba.conf
# ships `host ... scram-sha-256` rules, which happily accept an unencrypted
# connection - so a server that looks TLS-protected would still take cleartext
# from anything that can reach the port. The application always asks for
# `sslmode=require`, but the server should not be the one leaving the door open.
#
# Unix-socket (`local`) rules are deliberately left alone: they never touch a
# network, and both the healthcheck (pg_isready) and `compose exec postgres
# psql` rely on them.
set -eu

if [ "${REQUIRE_TLS:-false}" != "true" ]; then
  echo "[init] REQUIRE_TLS is not 'true' - leaving pg_hba.conf accepting plain TCP."
  exit 0
fi

PGHBA="${PGDATA:-/var/lib/postgresql/data}/pg_hba.conf"

if [ ! -f "$PGHBA" ]; then
  echo "[init] ERROR: $PGHBA not found - refusing to continue." >&2
  exit 1
fi

# "host" matches both TLS and non-TLS; "hostssl" matches only TLS. Rewriting the
# keyword in place preserves every rule's database/user/address/method columns.
sed -i 's/^host\([[:space:]]\)/hostssl\1/' "$PGHBA"

if grep -qE '^host[[:space:]]' "$PGHBA"; then
  echo "[init] ERROR: plain 'host' rules survived in pg_hba.conf:" >&2
  grep -nE '^host[[:space:]]' "$PGHBA" >&2
  exit 1
fi

echo "[init] TLS is now required for all TCP connections:"
grep -E '^hostssl' "$PGHBA" || true
