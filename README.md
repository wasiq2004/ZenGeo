# CheckGEO.ai

A self-hosted web app that scores how visible and citable a business is inside
AI-generated answers — ChatGPT, Claude, Perplexity — and produces a report with
prioritised fixes.

Users bring their own LLM API keys. Keys are encrypted at rest, used only for
that user's own audits, and never billed centrally, which is what keeps the tool
free and keeps anyone from imposing a limit on how much a user tests.

---

## Contents

- [What it measures](#what-it-measures)
- [Database](#database)
- [Email delivery](#email-delivery)
- [Quick start (local)](#quick-start-local)
- [First admin](#first-admin)
- [Connecting an AI provider key](#connecting-an-ai-provider-key)
- [Deploying to a VPS](#deploying-to-a-vps)
- [Self-hosted database VPS](#self-hosted-database-vps)
- [Backups and restore](#backups-and-restore)
- [Everyday commands](#everyday-commands)
- [Architecture](#architecture)
- [Security notes](#security-notes)
- [Adding a new AI provider](#adding-a-new-ai-provider)
- [Troubleshooting](#troubleshooting)

---

## What it measures

The GEO score is a 0–100 composite of seven weighted pillars. Each is scored
0–100 on its own, then combined by weight.

| # | Pillar | Weight | What it checks |
|---|--------|--------|----------------|
| 1 | Crawlability & AI bot access | 15% | Whether GPTBot, ClaudeBot, PerplexityBot, Google-Extended and CCBot are allowed; whether pages return real content without JavaScript; sitemap; HTTPS |
| 2 | llms.txt brand file | 10% | Presence, MIME type, spec structure, `llms-full.txt`, robots reference, smart-typography characters |
| 3 | Structured data | 15% | Organization / Product / FAQPage / Article JSON-LD, scored on presence *and* field completeness |
| 4 | Content extractability | 20% | Heading hierarchy, a direct answer in the first 200 words, lists and tables, paragraph length, quotable numeric claims |
| 5 | Evidence & E-E-A-T | 15% | Statistics, outbound citations, quotes, bylines, content freshness, vague superlatives |
| 6 | Entity authority | 10% | Live Wikidata lookup, `sameAs` profiles, name/address/phone consistency, third-party mentions |
| 7 | **AI Share of Voice** | 15% | Your own target prompts sent to the assistants you connected, checked for mentions, citations, position and which competitors appeared instead |

**Bands:** 0–39 Poor · 40–59 Needs Work · 60–79 Good · 80–100 Excellent.

**If no API key is connected**, pillar 7 is skipped and its 15% is redistributed
proportionally across the other six, so the score stays on a true 0–100 scale
rather than being silently capped at 85. The report says so explicitly.

---

## Database

**Postgres runs in Docker, in both stacks.** `docker compose up` starts the
database alongside everything else — there is nothing external to provision and
nothing to point at. Redis is local for the same reason it always was: it holds
only rate-limit counters and the Celery queue, nothing whose loss needs to
outlive a restart.

The production database is a container **on the application box**, and that
trade has a price worth stating plainly:

- Losing the VPS loses the application *and* the data together. Backups stop
  being optional — see [Backups and restore](#backups-and-restore), and set
  `BACKUP_REMOTE` so dumps leave the machine.
- `docker compose down -v` deletes the production database. The two stacks use
  different Compose **project names** (`geo-audit` for development,
  `geo-audit-prod` for production) precisely so a command aimed at the
  development file can never reach production's volumes.

In production the Postgres container mints a self-signed certificate on first
boot, serves TLS, and rewrites `pg_hba.conf` so unencrypted TCP is refused
outright — `sslmode=require` (encrypt, do not verify the chain) is exactly the
right client mode against it. The development container serves plain TCP and its
app connects with `sslmode=disable`; that traffic never leaves your machine.

If you would rather use a managed provider, nothing stops you: set
`DATABASE_URL` and `MIGRATIONS_DATABASE_URL` in `.env`, point them at the
provider with TLS requested, and remove the `postgres` service from
`docker-compose.prod.yml`. [Self-hosted database VPS](#self-hosted-database-vps)
remains as the runbook for running Postgres on a **separate** box, which is the
right move once the data outgrows sharing a disk with the app.

### Two roles, least privilege

| Role | Env vars | Used by | Rights |
|---|---|---|---|
| Owner | `POSTGRES_USER` / `POSTGRES_PASSWORD` | Alembic migrations, the one-time bootstrap, `pg_dump` | Owns the schema |
| Runtime | `APP_DB_USER` / `APP_DB_PASSWORD` | The API and the worker | `SELECT/INSERT/UPDATE/DELETE` only — no DDL |

The split means a SQL-injection foothold in the application cannot reshape the
schema. You can confirm it holds at any time:

```bash
# As the runtime role: reads work, DDL does not.
psql "$DATABASE_URL_LIBPQ" -c 'create table nope(id int)'
# ERROR:  permission denied for schema public
```

### The runtime role is created automatically

Both stacks run Postgres in a container, so the image's
`docker-entrypoint-initdb.d` hook does this on the first start of a fresh data
volume — there is no manual bootstrap step on first deploy any more.

Because that hook only fires on an empty data directory, editing the SQL has no
effect on a database that already exists. Re-apply it by hand in that case:

```bash
make db-bootstrap          # or: .\geo.ps1 db-bootstrap
```

Either wrapper runs [`infra/postgres/bootstrap/10-roles.sql`](infra/postgres/bootstrap/10-roles.sql)
through `psql`. To run it directly instead:

```bash
psql "$MIGRATIONS_DATABASE_URL" \
     -v app_user="$APP_DB_USER" \
     -v app_password="$APP_DB_PASSWORD" \
     -f infra/postgres/bootstrap/10-roles.sql
```

It is idempotent — re-running it resets the runtime role's password and
re-applies the grants. It creates the `citext` extension too, which
`users.email` needs; if your provider gates extensions, allowlist `citext`
first. The local dev container runs the very same file on first boot, so dev and
production privileges cannot drift apart.

### TLS

The hop to the database leaves this box, so it must be encrypted.
`POSTGRES_SSLMODE=require` is the minimum and the app **refuses to start in
production** with anything weaker. Prefer `verify-full` with
`POSTGRES_SSLROOTCERT` pointing at the CA that issued the server's certificate
— `require` encrypts the connection but does not prove who is on the other end
of it, so it stops passive sniffing but not an active man-in-the-middle.

Note the two spellings if you set the DSNs explicitly: asyncpg wants `?ssl=`,
libpq-based psycopg wants `?sslmode=`. Getting this wrong connects in cleartext
rather than failing, which is why the production check inspects both.

---

## Email delivery

Transactional mail (verification, password reset, email-change notice, audit
complete) goes through **Resend**. The transport is chosen automatically:

| Condition | Transport |
|---|---|
| `RESEND_API_KEY` set | Resend HTTP API |
| Only `SMTP_HOST` set | SMTP |
| Neither | Console — written to the backend log, never sent |

`RESEND_API_KEY` is **required in production**; the app refuses to boot without
it, because the console backend silently swallowing a password-reset link is the
kind of failure nobody notices until a user cannot get back in.

```dotenv
RESEND_API_KEY=re_...
MAIL_FROM=CheckGEO.ai <no-reply@yourdomain.example>
```

`MAIL_FROM` is parsed with the stdlib RFC 5322 parser into a display name and a
bare address, and sent as Resend's `from`. Production also rejects a
`MAIL_FROM` that is malformed, still on `example.com`, or missing a display name.

### Required first-deploy step: verify the sending domain

**Sends from an unverified domain are rejected or land in spam.** This cannot be
done from the codebase — it is a dashboard-and-DNS job, and it must happen before
the first real signup:

1. In the [Resend dashboard](https://resend.com/domains), add the domain part of
   your `MAIL_FROM` address as a sending domain.
2. Resend shows a set of DNS records. Publish all of them at whoever hosts that
   domain's DNS:
   - **SPF** — a `TXT` record authorising Resend to send for the domain.
   - **DKIM** — the `CNAME`/`TXT` records Resend gives you. This is what
     cryptographically signs your mail; without it you are unauthenticated.
   - **DMARC** — a `_dmarc` `TXT` record. Start at `p=none` while you confirm
     delivery, then tighten to `p=quarantine` and eventually `p=reject`.
     Publishing DKIM and SPF without DMARC leaves receivers no policy to apply.
3. Wait for the dashboard to show the domain **Verified**. DNS propagation is
   usually minutes but can take hours.
4. Confirm end to end with the test-send endpoint below — do not wait for a real
   user to discover it is broken.

### Confirming it works after deploy

```bash
curl -X POST https://your-domain/api/v1/admin/email/test-send \
     -H "Authorization: Bearer $ADMIN_ACCESS_TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{}'                      # omit "to" and it goes to your own address
```

Admin-only, rate-limited to 10/hour, and written to the admin audit log — it can
be pointed at an arbitrary address, so it is treated as a privileged action. It
sends synchronously and reports the provider's answer rather than queueing, so a
failure surfaces in the response instead of a worker log:

```json
{
  "delivered": true,
  "backend": "resend",
  "to": "admin@yourdomain.example",
  "sending_domain": "yourdomain.example",
  "provider_message_id": "4ef9a417-…",
  "detail": "Accepted by Resend. Check the inbox, and the spam folder …"
}
```

`delivered: true` means Resend *accepted* the message. Landing in spam is a
separate problem, and it means the SPF/DKIM/DMARC records need attention.

### How sends are queued

Everything except the test endpoint goes through the Celery worker, so a slow or
failing provider never holds up the request that triggered it. The task retries
up to 5 times with jittered exponential backoff (10s, capped at 10 minutes) —
jittered so a provider incident does not turn the queue into a synchronised
retry storm. Each send logs the Resend message id and HTTP status.

The queue payload is the render context, not a rendered body: it keeps the Redis
entry small, and a template fix reaches anything still waiting. If the broker is
unreachable the message is sent inline instead — losing a verification link
silently is worse than a slow signup.

---

## Quick start (local)

Requirements: Docker and Docker Compose. Nothing else.

```bash
git clone <your-repo-url> checkgeo
cd checkgeo
```

**1. Create `.env` with generated secrets.**

```bash
cp .env.example .env          # then fill in the secrets, or:
./geo.ps1 init                # Windows: generates all secrets for you
make secrets                  # Linux/macOS: prints values to paste in
```

Three secrets must be unique per environment:

| Variable | Generate with |
|---|---|
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `POSTGRES_PASSWORD` / `APP_DB_PASSWORD` | `openssl rand -base64 24` |

> **`ENCRYPTION_KEY` is not rotatable in place.** It encrypts every stored API
> key. If you lose it, users must re-enter their keys. Back it up somewhere
> separate from the database. To rotate, put the new key in `ENCRYPTION_KEY` and
> the old one in `ENCRYPTION_KEY_FALLBACKS` (comma-separated) so existing
> records still decrypt while they are re-saved.

Leave `DATABASE_URL` and `MIGRATIONS_DATABASE_URL` commented out for local work.
The dev override redirects `POSTGRES_HOST` at the throwaway container and turns
TLS off, and it can only do that if the DSN is being built from the components
rather than handed over whole.

**2. Start everything.**

```bash
docker compose up -d --build     # or: make up / .\geo.ps1 up
```

**3. Apply migrations.**

```bash
docker compose exec backend alembic upgrade head    # make migrate
```

**4. Open <http://localhost:8080>.**

The API docs are at <http://localhost:8080/docs> in development (disabled
automatically when `ENVIRONMENT=production`).

**Use `:8080`, not `:5173`.** Caddy puts the SPA and the API on one origin,
which the auth design depends on: the refresh cookie is `SameSite=Strict` and
path-scoped, so a session opened against the bare Vite dev server will not
survive a reload. The dev server does proxy `/api` and `/health` through to the
backend, so `:5173` is not a dead end if you land on it — but `:8080` is the
supported entry point.

---

## First admin

There is no way to sign up as an administrator — the signup endpoint rejects a
`role` field outright. The first admin is seeded from `.env`:

```bash
# Set FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD in .env first
docker compose exec backend python -m app.scripts.seed_admin   # make seed-admin
```

It is idempotent: run it again and it promotes the existing account rather than
failing, and it never overwrites a password.

Then sign in at the normal `/login` page — there is one login page for everyone,
and the role in the response decides whether you land on `/app` or `/admin`.
Further admins are promoted from **Admin → Users**.

---

## Connecting an AI provider key

Share of Voice — the pillar that actually tests whether assistants mention you —
runs on the user's own key.

1. Sign in and go to **Settings → API keys**.
2. Choose a provider, paste the key, optionally name a model.
3. Save. The key is verified against the provider *before* it is stored, using a
   free metadata endpoint where one exists (OpenAI and Anthropic), so checking a
   key costs nothing.

| Provider | Where to get a key | Notes |
|---|---|---|
| OpenAI | <https://platform.openai.com/api-keys> | Answers come from model knowledge; citations are whatever URLs appear in the text |
| Anthropic | <https://console.anthropic.com/settings/keys> | Can answer with live web search — enable it for comparable citation rates |
| Perplexity | <https://www.perplexity.ai/settings/api> | Always web-grounded and always returns citations |

**Citation rates only compare fairly between web-grounded providers**, which is
why the report labels each answer with whether it was grounded.

There is **no cap** on how many target prompts or providers a single audit uses.
The wizard shows `prompts × providers = planned API calls` before you start so
the spend is visible; calls are queued with a per-provider concurrency limit,
which exists so one large audit cannot trip a provider's rate limit — it is not
a usage restriction.

---

## Deploying to a VPS

One box running Docker Compose. Everything — Postgres, Redis, the API, the
worker, the built frontend and the TLS proxy — runs there, from a single file.

### Sizing

| Users | vCPU | RAM | Disk |
|---|---|---|---|
| Evaluation / single team | 2 | 2 GB | 20 GB |
| Small production (tens of users) | 2–4 | 4 GB | 40 GB |
| Busy (many concurrent audits) | 4–8 | 8 GB | 80 GB+ |

**RAM is the binding constraint**, and it is the worker that eats it — WeasyPrint
holds a whole document in memory, and Argon2id is deliberately memory-hard at
64 MiB per password verification. Redis, the API and the frontend are modest.
These figures are roughly half what they were when Postgres lived on the same
box; size the database separately at your provider.

Disk now grows mainly with stored PDF reports (~50–150 KB each), since the
database no longer sits on this volume.

### First deploy

```bash
# On the VPS
git clone <your-repo-url> /opt/checkgeo
cd /opt/checkgeo

cp .env.example .env
# Edit .env: set ENVIRONMENT=production, PUBLIC_DOMAIN, ACME_EMAIL,
# FRONTEND_URL=https://your-domain, CORS_ORIGINS=https://your-domain,
# RESEND_API_KEY, MAIL_FROM, and freshly generated secrets.
# The POSTGRES_* values create the database container - leave POSTGRES_HOST
# as "postgres" and just set strong passwords.

# That is the whole deploy. It builds the images, starts Postgres, Redis, the
# API, the worker, the frontend and Caddy, and a one-shot `init` service
# applies the migrations and creates the first admin.
docker compose -f docker-compose.prod.yml up -d --build

# Watch the one-shot job if you want to see the migrations land:
docker compose -f docker-compose.prod.yml logs -f init
```

Point an A record at the domain **before** the first start — Caddy obtains a
Let's Encrypt certificate on boot and needs the domain to resolve.

The database is not published to the host: it is reachable only from the Compose
network. Do not add a `ports:` entry for it. For a session, go through the
container:

```bash
make prod-psql             # or: .\geo.ps1 prod-psql
```

The app refuses to start in production with placeholder secrets, a plain-HTTP
`FRONTEND_URL`, or `ALLOW_PRIVATE_NETWORK_FETCH=true`. That is deliberate: those
are the mistakes worth failing loudly on.

### Firewall

Only the proxy is exposed. Redis has no `ports:` entry in the production compose
file, so it is reachable only on the internal Docker network, and Postgres is
not on this box at all.

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp        # SSH - restrict to your own IP if you can
ufw allow 80/tcp        # required for Let's Encrypt challenges
ufw allow 443/tcp
ufw allow 443/udp       # HTTP/3
ufw enable
```

Do **not** open 5432 or 6379 inbound — nothing needs to reach into this box on
either. The database connection is outbound only. For an interactive session
use `make psql` (or `.\geo.ps1 psql`), which runs a client container against the
configured DSN.

### Updating

```bash
cd /opt/checkgeo
./infra/backup/pg_backup.sh        # or rely on your provider's snapshot
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

---

## Self-hosted database VPS

> **Not the default any more.** The production stack runs Postgres in a
> container on the application box, and nothing in this section is required to
> deploy. Keep it for the day the database should move to its own machine —
> because it has outgrown sharing a disk with the app, or because you want
> losing one box to stop meaning losing both. Moving is: stand up the box below,
> restore a dump into it, point `DATABASE_URL` / `MIGRATIONS_DATABASE_URL` at
> it, and delete the `postgres` service from `docker-compose.prod.yml`.

Running Postgres yourself on a separate box means five things nobody else is
doing for you. Work through them **on the database box** before pointing the app
at it. Throughout: `APP_VPS_IP` is the application server's address, `DB_VPS_IP`
is this one's.

### 1. Server-side TLS

`POSTGRES_SSLMODE=require` asks the *client* to demand TLS. If the server is not
offering it, the connection fails outright — this is the step people skip and
then debug for an hour.

```bash
# Simplest: a self-signed cert. Fine when the app pins it with verify-full.
sudo -u postgres openssl req -new -x509 -days 3650 -nodes \
  -out /var/lib/postgresql/server.crt \
  -keyout /var/lib/postgresql/server.key \
  -subj "/CN=$DB_VPS_IP"
sudo -u postgres chmod 600 /var/lib/postgresql/server.key
```

In `postgresql.conf`:

```conf
ssl = on
ssl_cert_file = '/var/lib/postgresql/server.crt'
ssl_key_file  = '/var/lib/postgresql/server.key'
ssl_min_protocol_version = 'TLSv1.2'
```

Postgres refuses to start if the key is group- or world-readable, which is why
the `chmod 600` is not optional.

To use `verify-full` from the app — worth doing, since it is what actually stops
an active man-in-the-middle — copy `server.crt` to the app VPS, mount it into
the backend container, and set `POSTGRES_SSLROOTCERT` to that path *inside the
container*. With a self-signed cert the `CN` must match the `POSTGRES_HOST` value
exactly.

### 2. `listen_addresses` — do not open it wide

```conf
# NOT '*'. Bind only to the interface the app reaches you on - ideally a
# private network shared by the two boxes, so 5432 never touches the internet.
listen_addresses = '10.0.0.2'      # this box's private IP, plus 'localhost'
```

If your provider offers a private network or VPC between droplets, use it and
put the private address here. That single change does more for the security of
this setup than everything else on this list.

### 3. `pg_hba.conf` — one host, TLS-only

```conf
# TYPE     DATABASE   USER          ADDRESS           METHOD
hostssl    geo_audit  geo_runtime   10.0.0.1/32       scram-sha-256
hostssl    geo_audit  geo_app       10.0.0.1/32       scram-sha-256
local      all        postgres                        peer
```

`hostssl`, never `host`: a `host` line accepts unencrypted connections, so a
client that fails to negotiate TLS is let in rather than rejected. `/32` is a
single address — never `0.0.0.0/0`. Reload with `sudo systemctl reload postgresql`.

### 4. Firewall — 5432 is not a public port

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp                              # SSH, ideally from your IP only
ufw allow from 10.0.0.1 to any port 5432      # ONLY the app VPS
ufw enable
ufw status verbose                            # confirm 5432 is not open to Anywhere
```

Verify from somewhere else that it is genuinely closed:

```bash
nc -zv "$DB_VPS_IP" 5432     # from a third machine: must time out or be refused
```

### 5. Create the roles

Once, from the **app VPS** so the connection path is the one you are about to
rely on — if this step cannot connect, neither will the app:

```bash
cd /opt/checkgeo
make db-bootstrap            # or: .\geo.ps1 db-bootstrap
```

Then apply migrations and confirm the privilege split took:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
make psql -c 'create table nope(id int)'   # as geo_runtime: permission denied
```

### Checking it end to end

```bash
curl -fsS https://your-domain/healthz
# {"status":"ok","database":"reachable","elapsed_ms":3.1}
```

If the app cannot reach the database it **exits on startup** rather than booting
and 500-ing every request, and the log names the likely cause:

```
database_unreachable_on_startup host=10.0.0.2 port=5432 sslmode=require
  error=ConnectionRefusedError
  hint=Check pg_hba.conf allows this host over hostssl, that the server has
       ssl=on, and that the runtime role's password is current.
```

Point uptime monitoring at `/healthz`, not `/health`: `/health` only says the
process is running, and the whole failure mode worth catching here is the link
between the two boxes dropping while the app itself is perfectly fine.

---

## Backups and restore

Self-hosting Postgres means there is no snapshot feature and nothing else
watching: this cron job **is** the backup story.

```bash
crontab -e
# Nightly at 03:00, with each dump copied straight off this machine.
0 3 * * * cd /opt/checkgeo && BACKUP_REMOTE=user@backup-host:/srv/checkgeo-backups \
          ./infra/backup/pg_backup.sh >> /var/log/checkgeo-backup.log 2>&1
```

Run it on the VPS. It defaults to the production stack
(`docker compose -f docker-compose.prod.yml`); override `COMPOSE` to dump the
development one instead.

`pg_dump` runs **inside** the Postgres container over its local socket, using
the owner credentials already in that container's environment — no client image
to keep in step with the server version, no credentials on the command line, no
TLS handshake to satisfy. The script writes a compressed dump plus a tarball of
stored PDF reports into `./backups`, prunes anything older than
`RETENTION_DAYS` (default 14), and only publishes the final filename once the
dump completes — so an interrupted run cannot leave a half-written file that
looks like a good backup.

**Set `BACKUP_REMOTE`.** This matters more than it used to: the database is now
a container on this same box, so a dump in `./backups` sits on the same disk as
the thing it backs up. Losing the VPS loses the application, the database and
every local backup in one stroke. `BACKUP_REMOTE` is an `rsync`/`scp`
destination and a failed copy fails the whole run, so cron mails you — a backup
that quietly stopped replicating looks identical to a working one until the day
you need it. Without it the script still runs, but warns loudly.

**PDF reports are not in the database.** They live on a separate Docker volume,
which is why the script tars them separately. A database-only backup
restores every audit's scores and loses every generated report.

### Restore procedure

```bash
cd /opt/checkgeo
# 1. Fetch the dump back if it only exists off-box.
scp user@backup-host:/srv/checkgeo-backups/geo_audit-2026-07-30T03-00-00Z.sql.gz backups/

# 2. Restore. Names the target host and asks for confirmation before writing.
./infra/backup/pg_restore.sh backups/geo_audit-2026-07-30T03-00-00Z.sql.gz
```

The script stops the backend and worker first (restoring under live traffic
gives a torn result), streams the dump into the database through a client
container, restarts the services, and applies any migrations newer than the
dump. The dump is taken with `--clean --if-exists`, so it is safe to restore
over an existing database.

To restore the PDF reports as well:

```bash
docker compose exec -T backend tar -xzf - -C /data < <(gzip -dc backups/reports-2026-07-30T03-00-00Z.tar.gz)
```

Verify afterwards, rather than assuming:

```bash
curl -fsS https://your-domain/healthz          # database reachable
make psql -c 'select count(*) from users'      # rows actually came back
```

### Restore drill — do this before you need it

### Restore drill — do this before you need it

```bash
./infra/backup/pg_restore.sh backups/geo_audit-2026-07-30T03-00-00Z.sql.gz
```

It stops the backend and worker first (restoring under live traffic gives a torn
result), restores, restarts, and applies any migrations newer than the dump.

Practise on a throwaway copy. An untested restore path is the usual reason a
backup turns out not to be one.

---

## Everyday commands

Two runners are provided — `make` for Linux/macOS/VPS, `geo.ps1` for Windows.

| Task | Make | PowerShell |
|---|---|---|
| Start dev stack | `make up` | `.\geo.ps1 up` |
| Stop | `make down` | `.\geo.ps1 down` |
| Tail logs | `make logs S=backend` | `.\geo.ps1 logs backend` |
| Migrate | `make migrate` | `.\geo.ps1 migrate` |
| New migration | `make revision M="add x"` | `.\geo.ps1 revision "add x"` |
| Seed admin | `make seed-admin` | `.\geo.ps1 seed-admin` |
| Tests | `make test` | `.\geo.ps1 test` |
| Lint + types | `make lint` | `.\geo.ps1 lint` |
| Dependency audit | `make audit` | `.\geo.ps1 audit` |
| psql | `make psql` | `.\geo.ps1 psql` |
| Create runtime DB role (once) | `make db-bootstrap` | `.\geo.ps1 db-bootstrap` |
| Backup | `make backup` | `.\geo.ps1 backup` |
| Production up | `make prod-up` | `.\geo.ps1 prod-up` |

---

## Architecture

```
                ┌──────────────── the VPS ────────────────┐
Browser ─HTTPS─>│ Caddy ─┬──> /api/*  ──> FastAPI          │
                │        └──> /*      ──> nginx (SPA)      │
                │                                          │
                │  Celery worker      Redis                │
                │        │              │                  │
                │        └──────┬───────┘                  │
                │               ▼                          │
                │        Postgres 16  (TLS, hostssl-only,  │
                │                      no published port)  │
                └────────────────────┬─────────────────────┘
                                     │ HTTPS
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
              Resend API                   the sites being audited
            (transactional mail)           + the LLM providers
                                             (user's own keys)
```

- **Backend** — Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2.
- **Frontend** — TypeScript, React 18, Vite, Tailwind, TanStack Query, Recharts,
  Motion for the marketing-page animations.
- **Worker** — Celery. Audits fetch many external pages and can make a large
  number of LLM calls, so they never run inside a request.
- **Proxy** — Caddy rather than Nginx: on a single VPS it gets automatic
  Let's Encrypt certificates with three lines of config and renews them itself.
- **Database** — Postgres 16 in a container, reached over TLS on the Compose
  network and never published to the host; see [Database](#database). Moving it
  to its own machine later is [Self-hosted database VPS](#self-hosted-database-vps).
- **Email** — Resend, sent from the worker; see [Email delivery](#email-delivery).

Caddy is the only container that publishes ports.

### Typography

Two families, kept deliberately separate so the marketing site and the product
never drift into looking like each other:

| Surface | Family | Tailwind utility |
|---|---|---|
| Landing page, sign-in, sign-up | Poppins | `font-landing` |
| User panel, admin panel | Open Sans | `font-app` |

Both are self-hosted through `@fontsource` (see `src/styles/fonts.ts`) rather
than linked from a font CDN — no third-party request on first paint, no referrer
leaked to a font host, and no CSP exception needed. `font-app` is the inherited
default; the marketing tree opts into `font-landing` at its root.

---

## Security notes

Implemented, not aspirational — most of these have tests.

**Authentication**
- Argon2id password hashing (64 MiB, the hybrid variant), with automatic rehash
  when parameters are strengthened.
- Short-lived JWT access tokens in memory; the refresh token is an httpOnly,
  `Secure`, `SameSite=Strict`, path-scoped cookie that JavaScript cannot read.
- Refresh-token rotation with **reuse detection**: replaying a rotated token
  revokes the entire token family, because a replay means a copy leaked.
- CSRF double-submit on the cookie-authenticated endpoints, on top of SameSite.
- Per-IP *and* per-account rate limits on login, so a botnet rotating IPs still
  cannot grind one account. Exponential account lockout.
- Identical responses for "no such user" and "wrong password", and for password
  reset whether or not the address exists — no account enumeration.

**BYOK API keys**
- Encrypted with Fernet before insert; decrypted only in memory, inside the
  process making that user's own call.
- Never logged (the log pipeline redacts secret-shaped keys), never returned
  after creation, not visible to administrators, not included in data exports.
- Deleting a key is a hard delete, not a flag.

**SSRF** — the engine fetches URLs users type, from inside our network:
- Scheme and port allow-lists.
- Every address a hostname resolves to is checked; one public and one private
  record is rejected, not tolerated.
- The address actually connected to is re-checked after the socket opens, which
  closes the DNS-rebinding race a pre-flight lookup alone cannot win.
- Redirects are followed manually so every hop is revalidated.
- Response bodies are size-capped while streaming.

**Other**
- Postgres runs with two roles: Alembic migrates as the schema owner, the app
  connects as a DML-only role that cannot create, alter or drop objects.
- Security headers (CSP, HSTS in production, `X-Frame-Options: DENY`, nosniff,
  Referrer-Policy) set by both the app and the proxy, so the API is still
  protected if ever exposed without the proxy.
- CORS is an explicit allow-list; the config refuses to accept `*`.
- Containers run as non-root, with read-only root filesystems, dropped
  capabilities and `no-new-privileges` in production.
- Reports are stored on a private volume and served only through an endpoint
  that re-checks ownership — a non-owner gets 404, not 403, so the response does
  not confirm the audit exists.
- Every state-changing admin action is written to an append-only log with the
  actor, target and a reason.

**Dependencies** — pinned exactly, so they move only when Dependabot opens a PR
and CI goes green on it. Both audits run on every push and weekly on a schedule:
`pip-audit --strict` for Python, and `npm run audit:check` for JavaScript.

`audit:check` is a small gate rather than a bare `npm audit`, because npm offers
only "fail on everything" or "lower the threshold" — and neither is honest. It
fails on every high/critical advisory *except* those in
`frontend/scripts/audit-allowlist.json`, where each entry carries a written
reason it cannot affect this app and a date by which someone must look again.
An exception is a decision that is signed and expires, not a silently raised bar.

There is one such entry today: a React Router advisory affecting **RSC mode**.
This app uses React Router purely as a client-side URL matcher — no
`createBrowserRouter`, no loaders or actions, no server rendering — so the
vulnerable path is not shipped. npm's suggested remediation is a downgrade that
would reintroduce open-redirect CVEs which *are* reachable from `<Link>` and
`useNavigate`, so staying put is the safer position.

To report a vulnerability, open a private security advisory rather than a public
issue.

---

## Adding a new AI provider

The provider layer is a registry. Nothing outside it names a provider, so an
adapter is genuinely all it takes.

1. Create `backend/app/llm/yourprovider.py`:

```python
from app.llm.base import LLMProvider, LLMResponse, ValidationResult, register_provider

@register_provider
class YourProvider(LLMProvider):
    name = "yourprovider"
    display_name = "Your Provider"
    default_model = "their-best-model"
    suggested_models = ("their-best-model", "their-cheap-model")
    key_format_hint = "Starts with yp-"
    docs_url = "https://yourprovider.example/keys"
    supports_web_search = False

    async def validate(self) -> ValidationResult:
        ...   # prefer a free metadata endpoint over a billed completion

    async def ask(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        ...
```

2. Import it in `backend/app/llm/__init__.py`.
3. Add the value to the `LLMProviderName` enum and generate a migration.

The settings UI, the audit engine, the admin panel and the report all read from
the registry, so they pick it up with no further changes.

---

## Troubleshooting

**Audit stuck on "Queued".** The worker is not consuming. Check
`docker compose logs worker` and that Redis is healthy.

**Audit failed immediately with a crawlability score of 0.** The site was
unreachable, or the SSRF guard refused it. The per-stage event log on the audit
page gives the reason. Auditing a site on your own machine needs
`ALLOW_PRIVATE_NETWORK_FETCH=true`, which only works outside production.

**"Confirm your email before running an audit".** With no SMTP configured, the
verification link is written to the backend log instead of being emailed:

```bash
docker compose logs backend | grep -A3 email_console_backend
```

Set `SMTP_HOST` and friends to send real mail.

**Share of Voice always skipped.** Either no active API key, or no target
prompts in the questionnaire. Both are reported in the skip reason.

**PDF missing but the audit completed.** Report generation failures never fail
the audit — the results are already saved. Check the worker log for
`report_failed`.

**Certificate not issued.** Caddy needs the domain's DNS to resolve to the VPS
and ports 80 and 443 reachable from the internet. `docker compose logs caddy`
shows the ACME error.

**`got Future attached to a different loop` in the worker.** Every Celery task
must dispose the database engine before its event loop closes — use
`run_in_loop()` from `app/worker/tasks.py` rather than bare `asyncio.run`.

**404 on `/api/v1/...` from `http://127.0.0.1:5173`.** You are on the bare Vite
dev server. It proxies `/api` and `/health` to the backend, so this should work
— if it 404s, the proxy target is wrong for your setup: it defaults to the
`backend` Compose service, so set `VITE_DEV_PROXY_TARGET=http://localhost:8000`
when running Vite on the host instead of in Docker. Either way, prefer
<http://localhost:8080>; sessions are only fully supported on that origin.

**Backend will not start: "DATABASE_URL still contains an unexpanded `${...}`".**
The `.env` composes that value out of the other variables, and Docker Compose
expands the references when *it* loads the file. Anything else reading `.env`
directly — pytest, a bare `alembic` run, the app outside Compose — does not.
Write the value out literally, or leave it unset and let the app build the DSN
from the `POSTGRES_*` components.

**`connection requires a valid client certificate` / TLS errors on startup.**
Check `POSTGRES_SSLMODE` against what the provider expects, and remember the two
spellings: `?ssl=` for the asyncpg runtime DSN, `?sslmode=` for the psycopg
migration DSN. If you set `verify-full`, `POSTGRES_SSLROOTCERT` must point at a
CA file that exists *inside the container*, not on the host.

---

## Licence

Add the licence you intend to ship under before publishing this repository.
