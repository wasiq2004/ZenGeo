"""Create (or promote) the first administrator.

    docker compose exec backend python -m app.scripts.seed_admin

Reads FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD / FIRST_ADMIN_NAME from the
environment. Idempotent: running it again promotes the existing account rather
than failing, and never overwrites an existing password.

This is the only way an admin can come into existence - there is no code path
that lets a signup request choose its own role.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.models.user import User, UserRole
from app.db.session import session_scope
from app.services import auth_service

log = get_logger("seed_admin")


async def seed() -> int:
    email = settings.first_admin_email.strip()
    password = settings.first_admin_password.get_secret_value()

    if not email:
        log.error("seed_admin_failed", reason="FIRST_ADMIN_EMAIL is empty")
        return 1

    async with session_scope() as db:
        existing = await db.scalar(select(User).where(User.email == email))

        if existing:
            if existing.role is UserRole.admin:
                log.info("seed_admin_noop", email=email, note="already an administrator")
                return 0
            existing.role = UserRole.admin
            existing.is_email_verified = True
            log.info("seed_admin_promoted", email=email)
            return 0

        if len(password) < 12:
            log.error(
                "seed_admin_failed",
                reason="FIRST_ADMIN_PASSWORD must be at least 12 characters",
            )
            return 1

        await auth_service.create_user(
            db,
            email=email,
            password=password,
            full_name=settings.first_admin_name,
            role=UserRole.admin,
            email_verified=True,  # the operator set this address deliberately
        )
        log.info("seed_admin_created", email=email)
        return 0


def main() -> None:
    configure_logging(settings.log_level, settings.log_format)
    code = asyncio.run(seed())
    if code == 0:
        print(f"Admin ready: {settings.first_admin_email}")
        print("Sign in at the normal /login page - the role decides where you land.")
    sys.exit(code)


if __name__ == "__main__":
    main()
