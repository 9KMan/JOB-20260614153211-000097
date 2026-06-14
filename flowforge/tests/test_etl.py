"""ETL tests."""

from __future__ import annotations

from flowforge.services.etl import run_etl


def test_inline_etl():
    result = run_etl(
        {"kind": "inline", "data": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]},
        transform={"rename": {"name": "company"}},
    )
    assert result.total == 2
    assert result.succeeded == 2
    assert result.failed == 0


def test_inline_etl_pick():
    result = run_etl(
        {"kind": "inline", "data": [{"id": 1, "name": "A", "extra": "x"}]},
        transform={"pick": ["id", "name"]},
    )
    assert result.total == 1
    assert result.succeeded == 1


def test_json_text_etl():
    result = run_etl(
        {"kind": "json", "text": '[{"k":1},{"k":2},{"k":3}]'},
    )
    assert result.total == 3
    assert result.succeeded == 3


def test_csv_text_etl():
    csv = "id,name\n1,A\n2,B\n"
    result = run_etl({"kind": "csv", "text": csv})
    assert result.total == 2
    assert result.succeeded == 2
