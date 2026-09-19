from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select, update

from app.auth.tokens import ACCESS_COOKIE, REFRESH_COOKIE
from app.config import settings
from app.db import SessionLocal
from app.models import AuditLog, RefreshToken, UserRole
from tests.conftest import PASSWORD, MakeUser, login, use_only_refresh_cookie

NEW_PASSWORD = "Brand-New-Pass-77"


async def test_login_sets_cookies_and_me_returns_user(client: AsyncClient, make_user: MakeUser):
    await make_user("alice")
    r = await login(client, "alice", UserRole.TRAINEE)
    assert r.status_code == 200
    assert r.json()["role"] == "trainee"
    assert ACCESS_COOKIE in client.cookies and REFRESH_COOKIE in client.cookies
    set_cookie = " ".join(r.headers.get_list("set-cookie")).lower()
    assert "httponly" in set_cookie

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


async def test_wrong_password_unknown_user_and_wrong_role_get_same_error(client: AsyncClient, make_user: MakeUser):
    await make_user("bob", UserRole.TRAINER)
    responses = [
        await login(client, "bob", UserRole.TRAINER, "wrong"),
        await login(client, "nobody", UserRole.TRAINER),
        await login(client, "bob", UserRole.DEVELOPER),
    ]
    assert {r.status_code for r in responses} == {401}
    assert len({r.json()["detail"] for r in responses}) == 1


async def test_account_locks_after_repeated_failures(client: AsyncClient, make_user: MakeUser):
    await make_user("carol")
    for _ in range(settings.max_failed_logins):
        assert (await login(client, "carol", UserRole.TRAINEE, "wrong")).status_code == 401
    r = await login(client, "carol", UserRole.TRAINEE)  # correct password, but locked
    assert r.status_code == 423


async def test_login_rate_limit_per_ip(client: AsyncClient):
    codes = [(await login(client, f"ghost{i}", UserRole.TRAINEE)).status_code for i in range(12)]
    assert codes[: settings.login_rate_limit_per_minute] == [401] * settings.login_rate_limit_per_minute
    assert codes[-1] == 429


async def test_must_change_password_blocks_app_until_changed(client: AsyncClient, make_user: MakeUser):
    await make_user("dev", UserRole.DEVELOPER, must_change_password=True)
    r = await login(client, "dev", UserRole.DEVELOPER)
    assert r.json()["must_change_password"] is True
    assert (await client.get("/users")).status_code == 403

    weak = await client.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": "short"})
    assert weak.status_code == 422

    ok = await client.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    assert (await client.get("/users")).status_code == 200


async def test_role_based_access(client: AsyncClient, make_user: MakeUser):
    await make_user("tina")
    await make_user("root", UserRole.DEVELOPER)

    assert (await client.get("/users")).status_code == 401  # anonymous

    await login(client, "tina", UserRole.TRAINEE)
    assert (await client.get("/users")).status_code == 403  # trainee

    client.cookies.clear()
    await login(client, "root", UserRole.DEVELOPER)
    assert (await client.get("/users")).status_code == 200  # developer


async def test_refresh_rotates_and_replayed_token_ends_all_sessions(client: AsyncClient, make_user: MakeUser):
    await make_user("erin")
    await login(client, "erin", UserRole.TRAINEE)
    old_refresh = client.cookies.get(REFRESH_COOKIE)

    r = await client.post("/auth/refresh")
    assert r.status_code == 200
    new_refresh = client.cookies.get(REFRESH_COOKIE)
    assert new_refresh != old_refresh

    # Replaying the old token inside the grace window (two tabs) is refused but doesn't end the session
    use_only_refresh_cookie(client, old_refresh)
    assert (await client.post("/auth/refresh")).status_code == 401
    use_only_refresh_cookie(client, new_refresh)
    r = await client.post("/auth/refresh")
    assert r.status_code == 200
    latest = client.cookies.get(REFRESH_COOKIE)

    # Replaying after the grace window is treated as theft: every session of the user ends
    async with SessionLocal() as db:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.revoked_at.is_not(None))
            .values(revoked_at=datetime.now(UTC) - timedelta(minutes=5))
        )
        await db.commit()
    use_only_refresh_cookie(client, old_refresh)
    assert (await client.post("/auth/refresh")).status_code == 401
    use_only_refresh_cookie(client, latest)
    assert (await client.post("/auth/refresh")).status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient, make_user: MakeUser):
    await make_user("fred")
    await login(client, "fred", UserRole.TRAINEE)
    refresh_token = client.cookies.get(REFRESH_COOKIE)

    assert (await client.post("/auth/logout")).status_code == 204
    assert (await client.get("/auth/me")).status_code == 401
    use_only_refresh_cookie(client, refresh_token)
    assert (await client.post("/auth/refresh")).status_code == 401


async def test_login_attempts_are_audited(client: AsyncClient, make_user: MakeUser):
    await make_user("gina")
    await login(client, "gina", UserRole.TRAINEE, "wrong")
    await login(client, "gina", UserRole.TRAINEE)
    async with SessionLocal() as db:
        actions = list(await db.scalars(select(AuditLog.action).order_by(AuditLog.id)))
        assert actions == ["login_failed", "login"]
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.ip.is_not(None))) == 2
