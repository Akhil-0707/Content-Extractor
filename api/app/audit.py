import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def record(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    *,
    actor_id: uuid.UUID | None = None,
    request: Request | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Add an audit entry to the current transaction (committed with the caller's changes)."""
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before=before,
            after=after,
            ip=client_ip(request) if request else None,
        )
    )
