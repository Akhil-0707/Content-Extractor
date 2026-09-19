import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select, update

from app import audit
from app.access import add_member, load_class
from app.auth.deps import ActiveUser, DbSession, Staff, Trainee
from app.auth.rate_limit import enforce_rate_limit
from app.config import settings
from app.models import ClassAccessCode, ClassMember, ClassStatus, TrainingClass, User, UserRole, XpLedger

router = APIRouter(tags=["classes"])

# No 0/O or 1/I, so codes survive being read aloud or copied by hand
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


# ---------- schemas ----------


class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    initial_xp: int = Field(default=0, ge=0, le=100_000)
    status: ClassStatus = ClassStatus.ACTIVE
    # Developer only: which trainer owns the class. Trainers always own the classes they create.
    trainer_id: uuid.UUID | None = None


class ClassUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    initial_xp: int | None = Field(default=None, ge=0, le=100_000)
    status: ClassStatus | None = None
    trainer_id: uuid.UUID | None = None


class ClassOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: ClassStatus
    initial_xp: int
    trainer_id: uuid.UUID
    trainer_name: str
    member_count: int
    my_xp: int | None = None  # trainees only
    created_at: datetime


class MemberOut(BaseModel):
    user_id: uuid.UUID
    username: str
    full_name: str
    is_active: bool
    xp: int
    joined_at: datetime


class AddMembersIn(BaseModel):
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class TraineeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str


class AccessCodeIn(BaseModel):
    expires_in_hours: int | None = Field(default=72, ge=1, le=24 * 90)
    max_uses: int | None = Field(default=None, ge=1, le=1000)


class AccessCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    expires_at: datetime | None
    max_uses: int | None
    use_count: int
    revoked_at: datetime | None
    created_at: datetime


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)

    @field_validator("code")
    @classmethod
    def normalize(cls, v: str) -> str:
        return "".join(ch for ch in v.upper() if ch.isalnum())


# ---------- helpers ----------


def _member_count():
    return (
        select(func.count())
        .where(ClassMember.class_id == TrainingClass.id)
        .correlate(TrainingClass)
        .scalar_subquery()
    )


async def _class_out(db: DbSession, cls: TrainingClass, viewer: User) -> ClassOut:
    trainer_name = await db.scalar(select(User.full_name).where(User.id == cls.trainer_id))
    count = await db.scalar(select(func.count()).where(ClassMember.class_id == cls.id))
    my_xp = None
    if viewer.role == UserRole.TRAINEE:
        my_xp = await db.scalar(
            select(func.coalesce(func.sum(XpLedger.amount), 0)).where(
                XpLedger.class_id == cls.id, XpLedger.user_id == viewer.id
            )
        )
    return ClassOut(
        id=cls.id, name=cls.name, description=cls.description, status=cls.status, initial_xp=cls.initial_xp,
        trainer_id=cls.trainer_id, trainer_name=trainer_name or "", member_count=count or 0, my_xp=my_xp,
        created_at=cls.created_at,
    )


async def _require_trainer(db: DbSession, trainer_id: uuid.UUID) -> None:
    role = await db.scalar(select(User.role).where(User.id == trainer_id, User.is_active.is_(True)))
    if role != UserRole.TRAINER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "trainer_id must be an active trainer")


def _new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


# ---------- classes ----------


@router.get("/classes", response_model=list[ClassOut])
async def list_classes(user: ActiveUser, db: DbSession) -> list[ClassOut]:
    query = (
        select(TrainingClass, User.full_name, _member_count())
        .join(User, User.id == TrainingClass.trainer_id)
        .order_by(TrainingClass.created_at.desc())
    )
    xp_by_class: dict[uuid.UUID, int] = {}
    if user.role == UserRole.TRAINER:
        query = query.where(TrainingClass.trainer_id == user.id)
    elif user.role == UserRole.TRAINEE:
        query = query.join(ClassMember, ClassMember.class_id == TrainingClass.id).where(
            ClassMember.user_id == user.id, TrainingClass.status != ClassStatus.DRAFT
        )
        rows = await db.execute(
            select(XpLedger.class_id, func.sum(XpLedger.amount)).where(XpLedger.user_id == user.id).group_by(XpLedger.class_id)
        )
        xp_by_class = {class_id: int(total) for class_id, total in rows}

    result = await db.execute(query)
    return [
        ClassOut(
            id=cls.id, name=cls.name, description=cls.description, status=cls.status, initial_xp=cls.initial_xp,
            trainer_id=cls.trainer_id, trainer_name=trainer_name, member_count=count,
            my_xp=xp_by_class.get(cls.id, 0) if user.role == UserRole.TRAINEE else None,
            created_at=cls.created_at,
        )
        for cls, trainer_name, count in result
    ]


@router.post("/classes", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
async def create_class(body: ClassIn, request: Request, user: Staff, db: DbSession) -> ClassOut:
    if user.role == UserRole.TRAINER:
        trainer_id = user.id
    else:
        if body.trainer_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "trainer_id is required")
        await _require_trainer(db, body.trainer_id)
        trainer_id = body.trainer_id

    cls = TrainingClass(
        name=body.name.strip(), description=body.description, initial_xp=body.initial_xp, status=body.status,
        trainer_id=trainer_id, created_by=user.id,
    )
    db.add(cls)
    await db.flush()
    audit.record(db, "class_created", "class", cls.id, actor_id=user.id, request=request, after={"name": cls.name})
    await db.commit()
    await db.refresh(cls)
    return await _class_out(db, cls, user)


@router.get("/classes/{class_id}", response_model=ClassOut)
async def get_class(class_id: uuid.UUID, user: ActiveUser, db: DbSession) -> ClassOut:
    return await _class_out(db, await load_class(db, class_id, user), user)


@router.patch("/classes/{class_id}", response_model=ClassOut)
async def update_class(class_id: uuid.UUID, body: ClassUpdate, request: Request, user: Staff, db: DbSession) -> ClassOut:
    cls = await load_class(db, class_id, user, manage=True)
    changes = body.model_dump(exclude_unset=True)
    if "trainer_id" in changes:
        if user.role != UserRole.DEVELOPER:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the developer can reassign a class")
        await _require_trainer(db, changes["trainer_id"])
    before = {k: getattr(cls, k) for k in changes}
    for key, value in changes.items():
        setattr(cls, key, value)
    audit.record(
        db, "class_updated", "class", cls.id, actor_id=user.id, request=request,
        before={k: str(v) for k, v in before.items()}, after={k: str(v) for k, v in changes.items()},
    )
    await db.commit()
    await db.refresh(cls)
    return await _class_out(db, cls, user)


# ---------- members ----------


@router.get("/classes/{class_id}/members", response_model=list[MemberOut])
async def list_members(class_id: uuid.UUID, user: Staff, db: DbSession) -> list[MemberOut]:
    cls = await load_class(db, class_id, user, manage=True)
    xp = (
        select(func.coalesce(func.sum(XpLedger.amount), 0))
        .where(XpLedger.class_id == cls.id, XpLedger.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(User, ClassMember.joined_at, xp)
        .join(ClassMember, ClassMember.user_id == User.id)
        .where(ClassMember.class_id == cls.id)
        .order_by(User.full_name)
    )
    return [
        MemberOut(user_id=u.id, username=u.username, full_name=u.full_name, is_active=u.is_active, xp=x, joined_at=j)
        for u, j, x in rows
    ]


@router.post("/classes/{class_id}/members", response_model=list[MemberOut])
async def add_members(
    class_id: uuid.UUID, body: AddMembersIn, request: Request, user: Staff, db: DbSession
) -> list[MemberOut]:
    cls = await load_class(db, class_id, user, manage=True)
    ids = set(body.user_ids)
    trainees = set(
        await db.scalars(
            select(User.id).where(User.id.in_(ids), User.role == UserRole.TRAINEE, User.is_active.is_(True))
        )
    )
    if trainees != ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only active trainee accounts can be added to a class")
    added = [tid for tid in ids if await add_member(db, cls, tid, user.id)]
    audit.record(
        db, "members_added", "class", cls.id, actor_id=user.id, request=request,
        after={"user_ids": [str(i) for i in added]},
    )
    await db.commit()
    return await list_members(class_id, user, db)


@router.delete("/classes/{class_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(class_id: uuid.UUID, user_id: uuid.UUID, request: Request, user: Staff, db: DbSession) -> None:
    cls = await load_class(db, class_id, user, manage=True)
    result = await db.execute(
        delete(ClassMember).where(ClassMember.class_id == cls.id, ClassMember.user_id == user_id)
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this class")
    # XP history is kept: re-adding the trainee restores their total without a second initial grant
    audit.record(db, "member_removed", "class", cls.id, actor_id=user.id, request=request, after={"user_id": str(user_id)})
    await db.commit()


@router.get("/trainees", response_model=list[TraineeOut])
async def list_trainees(_: Staff, db: DbSession) -> list[User]:
    """Active trainee accounts a trainer can add to their classes."""
    return list(
        await db.scalars(
            select(User).where(User.role == UserRole.TRAINEE, User.is_active.is_(True)).order_by(User.full_name)
        )
    )


# ---------- access codes ----------


@router.get("/classes/{class_id}/access-codes", response_model=list[AccessCodeOut])
async def list_access_codes(class_id: uuid.UUID, user: Staff, db: DbSession) -> list[ClassAccessCode]:
    cls = await load_class(db, class_id, user, manage=True)
    return list(
        await db.scalars(
            select(ClassAccessCode)
            .where(ClassAccessCode.class_id == cls.id)
            .order_by(ClassAccessCode.created_at.desc())
        )
    )


@router.post("/classes/{class_id}/access-codes", response_model=AccessCodeOut, status_code=status.HTTP_201_CREATED)
async def create_access_code(
    class_id: uuid.UUID, body: AccessCodeIn, request: Request, user: Staff, db: DbSession
) -> ClassAccessCode:
    cls = await load_class(db, class_id, user, manage=True)
    expires_at = datetime.now(UTC) + timedelta(hours=body.expires_in_hours) if body.expires_in_hours else None
    for _ in range(5):  # collisions are astronomically unlikely, but be safe
        code = _new_code()
        if not await db.scalar(select(ClassAccessCode.id).where(ClassAccessCode.code == code)):
            break
    access_code = ClassAccessCode(
        class_id=cls.id, code=code, created_by=user.id, expires_at=expires_at, max_uses=body.max_uses
    )
    db.add(access_code)
    await db.flush()
    audit.record(db, "access_code_created", "class", cls.id, actor_id=user.id, request=request,
                 after={"code_id": str(access_code.id), "max_uses": body.max_uses})
    await db.commit()
    await db.refresh(access_code)
    return access_code


@router.delete("/classes/{class_id}/access-codes/{code_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_access_code(
    class_id: uuid.UUID, code_id: uuid.UUID, request: Request, user: Staff, db: DbSession
) -> None:
    cls = await load_class(db, class_id, user, manage=True)
    result = await db.execute(
        update(ClassAccessCode)
        .where(ClassAccessCode.id == code_id, ClassAccessCode.class_id == cls.id, ClassAccessCode.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Access code not found")
    audit.record(db, "access_code_revoked", "class", cls.id, actor_id=user.id, request=request,
                 after={"code_id": str(code_id)})
    await db.commit()


@router.post("/classes/join", response_model=ClassOut)
async def join_class(body: JoinIn, request: Request, user: Trainee, db: DbSession) -> ClassOut:
    await enforce_rate_limit(
        "join", str(user.id), settings.join_rate_limit_per_minute, "Too many attempts. Try again in a minute."
    )
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "This access code is invalid or has expired")
    now = datetime.now(UTC)
    code = await db.scalar(select(ClassAccessCode).where(ClassAccessCode.code == body.code))
    if code is None or code.revoked_at is not None or (code.expires_at and code.expires_at <= now):
        raise invalid
    cls = await db.get(TrainingClass, code.class_id)
    if cls is None or cls.status != ClassStatus.ACTIVE:
        raise invalid

    if not await add_member(db, cls, user.id, code.created_by):
        return await _class_out(db, cls, user)  # already a member: don't consume a use

    # Atomic use-count check, so two trainees can't both take the last use
    consumed = await db.scalar(
        update(ClassAccessCode)
        .where(
            ClassAccessCode.id == code.id,
            (ClassAccessCode.max_uses.is_(None)) | (ClassAccessCode.use_count < ClassAccessCode.max_uses),
        )
        .values(use_count=ClassAccessCode.use_count + 1)
        .returning(ClassAccessCode.id)
    )
    if consumed is None:
        await db.rollback()
        raise invalid
    audit.record(db, "class_joined", "class", cls.id, actor_id=user.id, request=request,
                 after={"code_id": str(code.id)})
    await db.commit()
    return await _class_out(db, cls, user)
