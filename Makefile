# CheckGEO.ai - task runner.
#
# Windows users without GNU make: use the equivalent PowerShell runner instead,
#   .\geo.ps1 up      .\geo.ps1 migrate      .\geo.ps1 seed-admin

# Two standalone stacks - the production file is not an overlay, so it takes a
# single -f. Do not combine them.
COMPOSE      := docker compose -f docker-compose.yml
COMPOSE_PROD := docker compose -f docker-compose.prod.yml
# Postgres now runs inside both stacks, so database work is `compose exec
# postgres` rather than a throwaway client joined to the network by hand. That
# also means psql talks over the local socket and never has to satisfy the
# server's TLS requirement.

.DEFAULT_GOAL := help
.PHONY: help secrets up down restart build logs ps migrate revision seed-admin \
        test test-backend test-frontend lint audit shell psql redis-cli \
        db-bootstrap backup dev-backup restore prod-up prod-down prod-logs prod-ps prod-migrate \
        prod-seed-admin prod-psql clean

help: ## Show available commands
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

secrets: ## Print freshly generated values for the three required secrets
	@echo "JWT_SECRET_KEY=$$(openssl rand -hex 32)"
	@echo "ENCRYPTION_KEY=$$(docker run --rm python:3.12-slim python -c \
		'from cryptography.fernet import Fernet' 2>/dev/null \
		|| python -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
	@echo "POSTGRES_PASSWORD=$$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
	@echo "APP_DB_PASSWORD=$$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"

up: ## Start the dev stack (hot reload) at http://localhost:8080
	$(COMPOSE) up -d --build
	@echo "App:  http://localhost:8080"
	@echo "Docs: http://localhost:8080/docs"

down: ## Stop the dev stack
	$(COMPOSE) down

restart: ## Restart backend and worker
	$(COMPOSE) restart backend worker

build: ## Rebuild all images
	$(COMPOSE) build

logs: ## Tail logs (make logs S=backend for one service)
	$(COMPOSE) logs -f --tail=120 $(S)

ps: ## Show container status
	$(COMPOSE) ps

migrate: ## Apply database migrations
	$(COMPOSE) exec backend alembic upgrade head

revision: ## Autogenerate a migration: make revision M="add widgets"
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(M)"

seed-admin: ## Create/promote the first admin from FIRST_ADMIN_* in .env
	$(COMPOSE) exec backend python -m app.scripts.seed_admin

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests (pytest)
	$(COMPOSE) exec backend pytest -q

test-frontend: ## Run frontend tests (vitest)
	$(COMPOSE) exec frontend npm run test

lint: ## Lint and type-check both sides
	$(COMPOSE) exec backend ruff check app tests
	$(COMPOSE) exec backend mypy app
	$(COMPOSE) exec frontend npm run typecheck

audit: ## Dependency vulnerability scan
	$(COMPOSE) exec backend pip-audit --strict --requirement requirements.txt
	$(COMPOSE) exec frontend npm run audit:check

shell: ## Shell inside the backend container
	$(COMPOSE) exec backend bash

# PGPASSWORD is required even inside the container: POSTGRES_INITDB_ARGS sets
# --auth-local=scram-sha-256, so the Unix socket asks for a password too. The
# value comes from the container's own environment, never the host's argv.
psql: ## psql session against the dev database
	$(COMPOSE) exec postgres sh -c 'PGPASSWORD="$$POSTGRES_PASSWORD" psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

db-bootstrap: ## Re-apply the runtime-role grants (already run on first start)
	$(COMPOSE) exec postgres sh -c 'PGPASSWORD="$$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 \
		-U "$$POSTGRES_USER" -d "$$POSTGRES_DB" \
		-v app_user="$$APP_DB_USER" -v app_password="$$APP_DB_PASSWORD" -f /bootstrap/10-roles.sql'

redis-cli: ## redis-cli session
	$(COMPOSE) exec redis redis-cli

# Both scripts default to the PRODUCTION stack - they are meant to run on the
# VPS. COMPOSE= overrides that for the dev stack.
backup: ## Compressed pg_dump of the PRODUCTION database into ./backups
	./infra/backup/pg_backup.sh

dev-backup: ## Same, but against the development database
	COMPOSE="docker compose -f docker-compose.yml" ./infra/backup/pg_backup.sh

restore: ## Restore into PRODUCTION: make restore F=backups/geo_audit-2026-07-30.sql.gz
	./infra/backup/pg_restore.sh $(F)

prod-up: ## Start the whole production stack (db, cache, api, worker, ui, proxy)
	$(COMPOSE_PROD) up -d --build
	@echo "Migrations and the first admin are applied by the one-shot 'init' service."
	@echo "Watch it with: make prod-logs S=init"

prod-down: ## Stop the production stack (volumes, and the database, are kept)
	$(COMPOSE_PROD) down

prod-logs: ## Tail production logs (make prod-logs S=backend for one service)
	$(COMPOSE_PROD) logs -f --tail=120 $(S)

prod-ps: ## Production container status
	$(COMPOSE_PROD) ps

prod-migrate: ## Apply migrations in production (also run automatically on up)
	$(COMPOSE_PROD) exec backend alembic upgrade head

prod-seed-admin: ## Create/promote the first admin in production
	$(COMPOSE_PROD) exec backend python -m app.scripts.seed_admin

prod-psql: ## psql session against the PRODUCTION database
	$(COMPOSE_PROD) exec postgres sh -c 'PGPASSWORD="$$POSTGRES_PASSWORD" psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

clean: ## Stop everything and DELETE local volumes (the LOCAL dev database only)
	@printf "This deletes the local dev database, Redis data and stored PDF reports.\nThe production stack uses a separate project name, so its database is NOT\ntouched by this. Type 'yes' to continue: " \
		&& read ans && [ "$$ans" = "yes" ] && $(COMPOSE) down -v || echo "Aborted."
