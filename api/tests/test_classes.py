from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app.db import SessionLocal
from app.main import app
from app.models import ClassAccessCode, UserRole
from tests.conftest import MakeUser, login


def new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def signed_in(make_user: MakeUser, username: str, role: UserRole) -> tuple[AsyncClient, str]:
    user = await make_user(username, role)
    c = new_client()
    assert (await login(c, username, role)).status_code == 200
    return c, str(user.id)


async def create_class(trainer: AsyncClient, **overrides) -> dict:
    r = await trainer.post("/classes", json={"name": "Python 101", "initial_xp": 50, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


async def test_trainer_sees_only_own_classes_developer_sees_all(make_user: MakeUser):
    t1, t1_id = await signed_in(make_user, "trainer1", UserRole.TRAINER)
    t2, _ = await signed_in(make_user, "trainer2", UserRole.TRAINER)
    dev, _ = await signed_in(make_user, "dev", UserRole.DEVELOPER)

    cls = await create_class(t1)
    assert cls["trainer_id"] == t1_id and cls["member_count"] == 0

    assert [c["id"] for c in (await t1.get("/classes")).json()] == [cls["id"]]
    assert (await t2.get("/classes")).json() == []
    assert (await t2.get(f"/classes/{cls['id']}")).status_code == 404
    assert (await t2.patch(f"/classes/{cls['id']}", json={"name": "Hijacked"})).status_code == 404
    assert [c["id"] for c in (await dev.get("/classes")).json()] == [cls["id"]]


async def test_developer_must_assign_class_to_a_trainer(make_user: MakeUser):
    dev, dev_id = await signed_in(make_user, "dev", UserRole.DEVELOPER)
    _, trainer_id = await signed_in(make_user, "trainer1", UserRole.TRAINER)

    assert (await dev.post("/classes", json={"name": "X"})).status_code == 422
    assert (await dev.post("/classes", json={"name": "X", "trainer_id": dev_id})).status_code == 400
    cls = await create_class(dev, trainer_id=trainer_id)
    assert cls["trainer_id"] == trainer_id


async def test_trainee_cannot_create_or_manage_classes(make_user: MakeUser):
    trainer, _ = await signed_in(make_user, "trainer1", UserRole.TRAINER)
    trainee, trainee_id = await signed_in(make_user, "amy", UserRole.TRAINEE)
    cls = await create_class(trainer)
    await trainer.post(f"/classes/{cls['id']}/members", json={"user_ids": [trainee_id]})

    assert (await trainee.post("/classes", json={"name": "Mine"})).status_code == 403
    assert (await trainee.get(f"/classes/{cls['id']}/members")).status_code == 403
    assert (await trainee.post(f"/classes/{cls['id']}/access-codes", json={})).status_code == 403
    assert (await trainee.get("/trainees")).status_code == 403


async def test_adding_members_grants_initial_xp_exactly_once(make_user: MakeUser):
    trainer, _ = await signed_in(make_user, "trainer1", UserRole.TRAINER)
    trainee, trainee_id = await signed_in(make_user, "amy", UserRole.TRAINEE)
    cls = await create_class(trainer, initial_xp=50)
    url = f"/classes/{cls['id']}/members"

    members = (await trainer.post(url, json={"user_ids": [trainee_id]})).json()
    assert [(m["username"], m["xp"]) for m in members] == [("amy", 50)]

    await trainer.post(url, json={"user_ids": [trainee_id]})  # again
    assert (await trainer.delete(f"{url}/{trainee_id}")).status_code == 204
    assert (await trainee.get(f"/classes/{cls['id']}")).status_code == 404  # removed → hidden
    members = (await trainer.post(url, json={"user_ids": [trainee_id]})).json()
    assert members[0]["xp"] == 50

    mine = (await trainee.get("/classes")).json()
    assert [(c["name"], c["my_xp"]) for c in mine] == [("Python 101", 50)]


async def test_only_active_trainees_can_be_added(make_user: MakeUser):
    trainer, _ = await signed_in(make_user, "trainer1", UserRole.TRAINER)
    _, other_trainer_id = await signed_in(make_user, "trainer2", UserRole.TRAINER)
    cls = await create_class(trainer)
    r = await trainer.post(f"/classes/{cls['id']}/members", json={"user_ids": [other_trainer_id]})
    assert r.status_code == 400


async def test_join_with_access_code(make_user: MakeUser):
    trainer, _ = await signed_in(make_user, "trainer1", UserRole.TRAINER)
    amy, _ = await signed_in(make_user, "amy", UserRole.TRAINEE)
    ben, _ = await signed_in(make_user, "ben", UserRole.TRAINEE)
    cls = await create_class(trainer, initial_xp=20)

    code = (await trainer.post(f"/classes/{cls['id']}/access-codes", json={"max_uses": 1})).json()
    assert len(code["code"]) == 8

    # Lower-case with a dash still works
    messy = f"{code['code'][:4].lower()}-{code['code'][4:]}"
    joined = await amy.post("/classes/join", json={"code": messy})
    assert joined.status_code == 200 and joined.json()["my_xp"] == 20

    # Joining again doesn't use up the code; the single use is gone for anyone else
    assert (await amy.post("/classes/join", json={"code": code["code"]})).status_code == 200
    assert (await ben.post("/classes/join", json={"code": code["code"]})).status_code == 400

    codes = (await trainer.get(f"/classes/{cls['id']}/access-codes")).json()
    assert codes[0]["use_count"] == 1


async def test_expired_revoked_and_draft_class_codes_are_rejected(make_user: MakeUser):
    trainer, _ = await signed_in(make_user, "trainer1", UserRole.TRAINER)
    amy, _ = await signed_in(make_user, "amy", UserRole.TRAINEE)
    cls = await create_class(trainer)
    codes_url = f"/classes/{cls['id']}/access-codes"

    revoked = (await trainer.post(codes_url, json={})).json()
    assert (await trainer.delete(f"{codes_url}/{revoked['id']}")).status_code == 204
    assert (await amy.post("/classes/join", json={"code": revoked["code"]})).status_code == 400

    expired = (await trainer.post(codes_url, json={})).json()
    async with SessionLocal() as db:
        await db.execute(
            update(ClassAccessCode)
            .where(ClassAccessCode.code == expired["code"])
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await db.commit()
    assert (await amy.post("/classes/join", json={"code": expired["code"]})).status_code == 400

    valid = (await trainer.post(codes_url, json={})).json()
    await trainer.patch(f"/classes/{cls['id']}", json={"status": "draft"})
    assert (await amy.post("/classes/join", json={"code": valid["code"]})).status_code == 400

    assert (await amy.post("/classes/join", json={"code": "NOPE2345"})).status_code == 400


async def test_draft_classes_hidden_from_members(make_user: MakeUser):
    trainer, _ = await signed_in(make_user, "trainer1", UserRole.TRAINER)
    amy, amy_id = await signed_in(make_user, "amy", UserRole.TRAINEE)
    cls = await create_class(trainer)
    await trainer.post(f"/classes/{cls['id']}/members", json={"user_ids": [amy_id]})
    assert len((await amy.get("/classes")).json()) == 1

    await trainer.patch(f"/classes/{cls['id']}", json={"status": "draft"})
    assert (await amy.get("/classes")).json() == []
    assert (await amy.get(f"/classes/{cls['id']}")).status_code == 404


async def test_only_developer_can_reassign_trainer(make_user: MakeUser):
    trainer, _ = await signed_in(make_user, "trainer1", UserRole.TRAINER)
    _, trainer2_id = await signed_in(make_user, "trainer2", UserRole.TRAINER)
    dev, _ = await signed_in(make_user, "dev", UserRole.DEVELOPER)
    cls = await create_class(trainer)

    assert (await trainer.patch(f"/classes/{cls['id']}", json={"trainer_id": trainer2_id})).status_code == 403
    r = await dev.patch(f"/classes/{cls['id']}", json={"trainer_id": trainer2_id})
    assert r.status_code == 200 and r.json()["trainer_id"] == trainer2_id
    assert (await trainer.get(f"/classes/{cls['id']}")).status_code == 404


async def test_join_attempts_are_rate_limited(make_user: MakeUser):
    amy, _ = await signed_in(make_user, "amy", UserRole.TRAINEE)
    codes = [(await amy.post("/classes/join", json={"code": f"BAD{i:05d}"})).status_code for i in range(11)]
    assert codes[-1] == 429
