"""Tests run against a real Postgres database and Redis (see scripts/test.sh), never the dev database."""

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.auth.rate_limit import redis
from app.auth.tokens import REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Base, User, UserRole
from app.security import hash_password

assert settings.database_url.rstrip("/").endswith("_test"), "Refusing to run tests against a non-test database"

PASSWORD = "Correct-Horse-42"

MakeUser = Callable[..., Awaitable[User]]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # One event loop for the whole run, shared with the app's DB and Redis connection pools
    for item in items:
        item.add_marker(pytest.mark.asyncio(loop_scope="session"), append=False)


def use_only_refresh_cookie(client: AsyncClient, token: str) -> None:
    client.cookies.clear()
    # Same domain/path the server uses, so the next Set-Cookie replaces it instead of adding a second one
    client.cookies.set(REFRESH_COOKIE, token, domain="testserver.local", path=REFRESH_COOKIE_PATH)


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with SessionLocal() as db:
        await db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await db.commit()
    await redis.flushdb()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


@pytest.fixture
def make_user() -> MakeUser:
    async def _make(
        username: str, role: UserRole = UserRole.TRAINEE, *, must_change_password: bool = False
    ) -> User:
        async with SessionLocal() as db:
            user = User(
                username=username,
                full_name=username.title(),
                role=role,
                password_hash=hash_password(PASSWORD),
                must_change_password=must_change_password,
            )
            db.add(user)
            await db.commit()
            return user

    return _make


async def login(client: AsyncClient, username: str, role: UserRole, password: str = PASSWORD):
    return await client.post("/auth/login", json={"username": username, "password": password, "role": role.value})
