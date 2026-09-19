from httpx import AsyncClient

from app.models import UserRole
from tests.conftest import MakeUser, login


async def _login_developer(client: AsyncClient, make_user: MakeUser) -> None:
    await make_user("root", UserRole.DEVELOPER)
    await login(client, "root", UserRole.DEVELOPER)


async def test_developer_creates_user_who_must_change_password(client: AsyncClient, make_user: MakeUser):
    await _login_developer(client, make_user)
    r = await client.post(
        "/users",
        json={"username": "new.trainee", "full_name": "New Trainee", "role": "trainee", "password": "Temp-Pass-123"},
    )
    assert r.status_code == 201
    assert r.json()["must_change_password"] is True

    client.cookies.clear()
    r = await login(client, "new.trainee", UserRole.TRAINEE, "Temp-Pass-123")
    assert r.status_code == 200 and r.json()["must_change_password"] is True


async def test_duplicate_username_and_weak_password_rejected(client: AsyncClient, make_user: MakeUser):
    await _login_developer(client, make_user)
    dup = await client.post(
        "/users", json={"username": "root", "full_name": "X", "role": "trainee", "password": "Temp-Pass-123"}
    )
    assert dup.status_code == 409
    weak = await client.post(
        "/users", json={"username": "weakling", "full_name": "X", "role": "trainee", "password": "password"}
    )
    assert weak.status_code == 422


async def test_deactivated_user_cannot_log_in_and_is_signed_out(client: AsyncClient, make_user: MakeUser):
    trainee = await make_user("tom")
    trainee_client = AsyncClient(transport=client._transport, base_url="http://testserver")
    await login(trainee_client, "tom", UserRole.TRAINEE)
    assert (await trainee_client.get("/auth/me")).status_code == 200

    await _login_developer(client, make_user)
    r = await client.patch(f"/users/{trainee.id}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False

    assert (await trainee_client.get("/auth/me")).status_code == 401
    assert (await trainee_client.post("/auth/refresh")).status_code == 401
    assert (await login(trainee_client, "tom", UserRole.TRAINEE)).status_code == 401
    await trainee_client.aclose()


async def test_developer_cannot_deactivate_self(client: AsyncClient, make_user: MakeUser):
    await _login_developer(client, make_user)
    me = (await client.get("/auth/me")).json()
    r = await client.patch(f"/users/{me['id']}", json={"is_active": False})
    assert r.status_code == 400
