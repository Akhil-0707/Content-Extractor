"""Create starter accounts and a demo class for development.

Usage (inside the api container):  python -m app.seed

Passwords are random and written to data/seed_credentials.txt (git-ignored), never printed.
Every seeded user must change their password on first login. Safe to re-run: existing users are skipped.
"""

import asyncio
import secrets
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import ClassMember, ClassStatus, TrainingClass, User, UserRole, XpLedger, XpReason
from app.security import hash_password

CREDENTIALS_FILE = Path("data/seed_credentials.txt")
DEMO_CLASS_NAME = "Demo class"
DEMO_INITIAL_XP = 100

ACCOUNTS = [
    ("developer", "Developer", UserRole.DEVELOPER),
    ("trainer1", "Trainer One", UserRole.TRAINER),
    ("trainee1", "Trainee One", UserRole.TRAINEE),
    ("trainee2", "Trainee Two", UserRole.TRAINEE),
    ("trainee3", "Trainee Three", UserRole.TRAINEE),
]


async def seed() -> None:
    created: list[tuple[str, str]] = []
    async with SessionLocal() as db:
        users: dict[str, User] = {}
        for username, full_name, role in ACCOUNTS:
            user = await db.scalar(select(User).where(User.username == username))
            if user is None:
                password = secrets.token_urlsafe(12)
                user = User(username=username, full_name=full_name, role=role, password_hash=hash_password(password))
                db.add(user)
                created.append((username, password))
            users[username] = user
        await db.flush()

        demo = await db.scalar(select(TrainingClass).where(TrainingClass.name == DEMO_CLASS_NAME))
        if demo is None:
            demo = TrainingClass(
                name=DEMO_CLASS_NAME,
                description="Sample class for local development",
                trainer_id=users["trainer1"].id,
                initial_xp=DEMO_INITIAL_XP,
                status=ClassStatus.ACTIVE,
                created_by=users["developer"].id,
            )
            db.add(demo)
            await db.flush()
            for user in users.values():
                if user.role is UserRole.TRAINEE:
                    db.add(ClassMember(class_id=demo.id, user_id=user.id, granted_by=users["trainer1"].id))
                    db.add(XpLedger(user_id=user.id, class_id=demo.id, amount=DEMO_INITIAL_XP, reason=XpReason.INITIAL))

        await db.commit()
    await engine.dispose()

    if created:
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CREDENTIALS_FILE.open("a", encoding="utf-8") as f:
            for username, password in created:
                f.write(f"{username}\t{password}\n")
        print(f"Created {len(created)} users; credentials written to {CREDENTIALS_FILE}")
    else:
        print("All seed users already exist; nothing created")


if __name__ == "__main__":
    asyncio.run(seed())
