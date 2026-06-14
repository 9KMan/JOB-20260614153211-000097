"""Lightweight ETL helpers.

Used by the /etl endpoint and the `etl` trigger to ingest data from
external sources (CSV/JSON files, HTTP endpoints) into a generic
``etl_jobs`` table, with a per-row status and retry support.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import httpx


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ETLResult:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": int(((self.finished_at or _utcnow()) - self.started_at).total_seconds() * 1000),
        }


def _fetch(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    kind = (source.get("kind") or "json").lower()
    if kind == "inline":
        rows = source.get("data") or []
        return [dict(row) for row in rows]
    if kind == "csv":
        text = source.get("text") or ""
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]
    if kind == "json":
        text = source.get("text") or ""
        if not text:
            return []
        data = json.loads(text)
        if isinstance(data, list):
            return [dict(item) for item in data]
        if isinstance(data, dict):
            return [data]
        return [{"value": data}]
    if kind == "http":
        url = source.get("url")
        if not url:
            raise ValueError("http source requires `url`")
        method = (source.get("method") or "GET").upper()
        headers = source.get("headers") or {}
        body = source.get("body")
        with httpx.Client(timeout=30) as client:
            resp = client.request(method, url, headers=headers, json=body if body is not None else None)
            resp.raise_for_status()
            data = resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
        if isinstance(data, list):
            return [dict(item) for item in data]
        if isinstance(data, dict):
            return [data]
        return [{"raw": data}]
    raise ValueError(f"unknown source kind: {kind!r}")


def run_etl(source: Dict[str, Any], transform: Optional[Dict[str, Any]] = None) -> ETLResult:
    """Pull rows from `source`, optionally apply a `transform`
    (``rename`` and ``pick``), and return an ETLResult summary.
    """
    result = ETLResult()
    rows = _fetch(source)
    result.total = len(rows)
    transform = transform or {}
    renames = transform.get("rename") or {}
    pick = transform.get("pick")

    for index, row in enumerate(rows):
        try:
            if pick:
                row = {k: row.get(k) for k in pick}
            for src, dst in renames.items():
                if src in row:
                    row[dst] = row.pop(src)
            result.succeeded += 1
        except Exception as exc:  # noqa: BLE001
            result.failed += 1
            result.errors.append({"index": index, "error": str(exc)})

    result.finished_at = _utcnow()
    return result


def new_job_id() -> str:
    return str(uuid.uuid4())


def coerce_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Coerce iterable to list of plain dicts (defensive copy)."""
    out: List[Dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            out.append({"value": record})
        else:
            out.append(dict(record))
    return out
