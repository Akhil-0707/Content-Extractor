import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

from app import audit
from app.auth.deps import CurrentUser, DbSession
from app.auth.passwords import validate_new_password
from app.auth.rate_limit import check_login_rate
from app.auth.tokens import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
    set_auth_cookies,
)
from app.config import settings
from app.models import RefreshToken, User, UserRole
from app.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against when the username doesn't exist, so response time doesn't reveal valid usernames
_DUMMY_HASH = hash_password("dummy-password-for-timing")

INVALID_LOGIN = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username, password or role")
LOCKED = HTTPException(status.HTTP_423_LOCKED, "Too many failed attempts. Account locked, try again later.")


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    role: UserRole


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str
    role: UserRole
    must_change_password: bool


async def _issue_tokens(db: DbSession, user: User, request: Request, response: Response) -> None:
    raw, token_hash = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
            user_agent=(request.headers.get("user-agent") or "")[:255] or None,
        )
    )
    set_auth_cookies(response, create_access_token(user), raw)


async def revoke_all_refresh_tokens(db: DbSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, request: Request, response: Response, db: DbSession) -> User:
    await check_login_rate(audit.client_ip(request))
    now = datetime.now(UTC)
    user = await db.scalar(select(User).where(User.username == body.username))

    if user is None:
        verify_password(_DUMMY_HASH, body.password)
        audit.record(db, "login_failed", "user", body.username, request=request, after={"reason": "unknown_user"})
        await db.commit()
        raise INVALID_LOGIN

    if user.locked_until and user.locked_until > now:
        audit.record(db, "login_blocked", "user", user.id, request=request)
        await db.commit()
        raise LOCKED

    password_ok = verify_password(user.password_hash, body.password)
    if not (password_ok and user.is_active and user.role == body.role):
        user.failed_login_count += 1
        reason = "bad_password" if not password_ok else "inactive" if not user.is_active else "wrong_role"
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_count = 0
            reason += "+locked"
        audit.record(db, "login_failed", "user", user.id, request=request, after={"reason": reason})
        await db.commit()
        raise INVALID_LOGIN

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await _issue_tokens(db, user, request, response)
    audit.record(db, "login", "user", user.id, actor_id=user.id, request=request)
    await db.commit()
    return user


@router.post("/refresh", response_model=UserOut)
async def refresh(request: Request, response: Response, db: DbSession) -> User:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    now = datetime.now(UTC)
    token = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)))
    if token is None or token.expires_at <= now:
        clear_auth_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    if token.revoked_at is not None:
        # A rotated token being replayed. A few seconds' grace covers two browser tabs refreshing at once;
        # anything later is treated as theft and ends every session of that user.
        if now - token.revoked_at > timedelta(seconds=30):
            await revoke_all_refresh_tokens(db, token.user_id)
            audit.record(db, "refresh_token_reuse", "user", token.user_id, request=request)
            await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    token.revoked_at = now
    await _issue_tokens(db, user, request, response)
    await db.commit()
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DbSession) -> None:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(raw), RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await db.commit()
    clear_auth_cookies(response)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/change-password", response_model=UserOut)
async def change_password(
    body: ChangePasswordIn, request: Request, response: Response, user: CurrentUser, db: DbSession
) -> User:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "New password must be different")
    validate_new_password(body.new_password, user.username)

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    # Sign out every other device, then give this one fresh tokens
    await revoke_all_refresh_tokens(db, user.id)
    await _issue_tokens(db, user, request, response)
    audit.record(db, "password_changed", "user", user.id, actor_id=user.id, request=request)
    await db.commit()
    return user
