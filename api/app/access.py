"""Who may see and manage a class.

- Developer: every class.
- Trainer: only classes they own (trainer_id).
- Trainee: only non-draft classes they are a member of; never manage.

Classes a user may not see answer 404 (not 403), so class ids can't be probed.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClassMember, ClassStatus, TrainingClass, User, UserRole, XpLedger, XpReason

CLASS_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Class not found")


async def is_member(db: AsyncSession, class_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        await db.scalar(
            select(ClassMember.user_id).where(ClassMember.class_id == class_id, ClassMember.user_id == user_id)
        )
    ) is not None


async def load_class(db: AsyncSession, class_id: uuid.UUID, user: User, *, manage: bool = False) -> TrainingClass:
    cls = await db.get(TrainingClass, class_id)
    if cls is None:
        raise CLASS_NOT_FOUND
    if user.role == UserRole.DEVELOPER:
        return cls
    if user.role == UserRole.TRAINER:
        if cls.trainer_id != user.id:
            raise CLASS_NOT_FOUND
        return cls
    if cls.status == ClassStatus.DRAFT or not await is_member(db, cls.id, user.id):
        raise CLASS_NOT_FOUND
    if manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for your role")
    return cls


async def add_member(db: AsyncSession, cls: TrainingClass, trainee_id: uuid.UUID, granted_by: uuid.UUID | None) -> bool:
    """Add a trainee and grant the class's initial XP once. Returns False if they were already a member."""
    added = await db.scalar(
        insert(ClassMember)
        .values(class_id=cls.id, user_id=trainee_id, granted_by=granted_by)
        .on_conflict_do_nothing()
        .returning(ClassMember.user_id)
    )
    if added and cls.initial_xp > 0:
        # Unique partial index: a trainee removed and re-added never gets the initial XP twice
        await db.execute(
            insert(XpLedger)
            .values(user_id=trainee_id, class_id=cls.id, amount=cls.initial_xp, reason=XpReason.INITIAL)
            # Literal predicate: Postgres can only match a partial index when the WHERE isn't a bind parameter
            .on_conflict_do_nothing(index_elements=["user_id", "class_id"], index_where=text("reason = 'initial'"))
        )
    return added is not None
