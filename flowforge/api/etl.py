"""ETL endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from flowforge.api.deps import get_current_user
from flowforge.api.schemas import ETLDryRunRequest, ETLResultOut
from flowforge.core.database import get_db
from flowforge.models.user import User
from flowforge.services import etl

router = APIRouter(prefix="/api/v1/etl", tags=["etl"])


@router.post("/run", response_model=ETLResultOut)
def run_etl(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
) -> ETLResultOut:
    """Run an ETL pipeline synchronously. The payload shape is::

        {
          "source": {"kind": "inline|csv|json|http", "data"|"text"|"url": ...},
          "transform": {"rename": {...}, "pick": [...]}
        }
    """
    source = payload.get("source")
    if not isinstance(source, dict):
        raise HTTPException(status_code=400, detail="source is required (object)")
    try:
        result = etl.run_etl(source, payload.get("transform"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"etl failed: {exc}") from exc
    return ETLResultOut(**result.to_dict())


@router.post("/dry-run", response_model=ETLResultOut)
def dry_run(
    payload: ETLDryRunRequest,
    current_user: User = Depends(get_current_user),
) -> ETLResultOut:
    """Run an ETL pipeline and return only the first N transformed rows."""
    try:
        result = etl.run_etl(payload.source, payload.transform)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"etl failed: {exc}") from exc
    return ETLResultOut(**result.to_dict())
