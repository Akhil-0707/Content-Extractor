"""Account management, developer only. Trainees and trainers never sign themselves up."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import audit
from app.auth.deps import DbSession, Developer
from app.auth.passwords import validate_new_password
from app.auth.router import revoke_all_refresh_tokens
from app.models import User, UserRole
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=128)
    role: UserRole
    password: str = Field(min_length=1, max_length=256)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=128)
    role: UserRole | None = None
    is_active: bool | None = None
    # Sets a temporary password the user must change at next login
    new_password: str | None = Field(default=None, min_length=1, max_length=256)
    unlock: bool = False


@router.get("", response_model=list[UserAdminOut])
async def list_users(_: Developer, db: DbSession, role: UserRole | None = None) -> list[User]:
    query = select(User).order_by(User.role, User.username)
    if role is not None:
        query = query.where(User.role == role)
    return list(await db.scalars(query))


@router.post("", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, request: Request, dev: Developer, db: DbSession) -> User:
    if await db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    validate_new_password(body.password, body.username)
    user = User(
        username=body.username,
        full_name=body.full_name,
        role=body.role,
        password_hash=hash_password(body.password),
        must_change_password=True,
    )
    db.add(user)
    await db.flush()
    audit.record(
        db, "user_created", "user", user.id, actor_id=dev.id, request=request,
        after={"username": user.username, "role": user.role.value},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserAdminOut)
async def update_user(user_id: uuid.UUID, body: UserUpdate, request: Request, dev: Developer, db: DbSession) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == dev.id and (body.is_active is False or (body.role and body.role != UserRole.DEVELOPER)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate or demote your own account")

    before = {"full_name": user.full_name, "role": user.role.value, "is_active": user.is_active}
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.new_password is not None:
        validate_new_password(body.new_password, user.username)
        user.password_hash = hash_password(body.new_password)
        user.must_change_password = True
    if body.unlock:
        user.locked_until = None
        user.failed_login_count = 0
    if body.is_active is False or body.new_password is not None or body.role is not None:
        await revoke_all_refresh_tokens(db, user.id)

    after = {"full_name": user.full_name, "role": user.role.value, "is_active": user.is_active}
    if body.new_password is not None:
        after["password_reset"] = True
    if body.unlock:
        after["unlocked"] = True
    audit.record(db, "user_updated", "user", user.id, actor_id=dev.id, request=request, before=before, after=after)
    await db.commit()
    await db.refresh(user)
    return user
