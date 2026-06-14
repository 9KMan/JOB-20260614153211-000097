"""Integration CRUD endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from flowforge.api.deps import get_current_user
from flowforge.api.schemas import IntegrationCreate, IntegrationOut
from flowforge.core.database import get_db
from flowforge.models.integration import Integration, IntegrationKind
from flowforge.models.user import User
from flowforge.services import audit

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


def _normalize_secret(payload: IntegrationCreate) -> dict:
    """Mask secret values for safe reads. We never echo them back via
    the API — only confirm presence.
    """
    masked = {}
    for key, value in (payload.secret or {}).items():
        if value in (None, ""):
            continue
        masked[key] = "********" if isinstance(value, str) and len(value) > 0 else "set"
    return masked


@router.post("", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
def create_integration(
    payload: IntegrationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Integration:
    try:
        kind = IntegrationKind(payload.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid kind: {payload.kind}") from exc
    existing = (
        db.query(Integration)
        .filter(Integration.owner_id == current_user.id, Integration.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="integration with that name already exists")
    integ = Integration(
        name=payload.name,
        kind=kind,
        config=payload.config or {},
        secret=payload.secret or {},
        is_active=payload.is_active,
        owner_id=current_user.id,
    )
    db.add(integ)
    db.flush()
    audit.record(
        db,
        action="integration.create",
        actor_id=current_user.id,
        target_type="integration",
        target_id=integ.id,
        payload={"name": integ.name, "kind": integ.kind.value},
    )
    db.commit()
    db.refresh(integ)
    return integ


@router.get("", response_model=List[IntegrationOut])
def list_integrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    kind: Optional[str] = None,
) -> List[Integration]:
    q = db.query(Integration).filter(Integration.owner_id == current_user.id)
    if kind:
        try:
            q = q.filter(Integration.kind == IntegrationKind(kind))
        except ValueError:
            pass
    return q.order_by(Integration.created_at.desc()).all()


@router.get("/{integration_id}", response_model=IntegrationOut)
def get_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Integration:
    integ = db.get(Integration, integration_id)
    if not integ or integ.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="integration not found")
    return integ


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    integ = db.get(Integration, integration_id)
    if not integ or integ.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="integration not found")
    audit.record(
        db,
        action="integration.delete",
        actor_id=current_user.id,
        target_type="integration",
        target_id=integ.id,
    )
    db.delete(integ)
    db.commit()
