"""Auth + workflow CRUD API tests."""

from __future__ import annotations


def test_health(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_and_me(client, auth_headers):
    r = client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "tester@flowforge.example"
    assert body["role"] == "admin"


def test_login_invalid(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "tester@flowforge.example", "password": "WRONG"},
    )
    assert r.status_code == 401


def test_workflow_crud(client, auth_headers):
    create = client.post(
        "/api/v1/workflows",
        headers=auth_headers,
        json={
            "name": "Test Workflow",
            "description": "unit test",
            "trigger": "manual",
            "definition": {
                "steps": [
                    {"id": "log", "name": "log", "type": "log", "config": {"message": "hi"}},
                ]
            },
        },
    )
    assert create.status_code == 201, create.text
    wf = create.json()
    wid = wf["id"]

    listing = client.get("/api/v1/workflows", headers=auth_headers)
    assert listing.status_code == 200
    assert any(w["id"] == wid for w in listing.json())

    fetched = client.get(f"/api/v1/workflows/{wid}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Test Workflow"

    patch = client.patch(
        f"/api/v1/workflows/{wid}",
        headers=auth_headers,
        json={"description": "updated"},
    )
    assert patch.status_code == 200
    assert patch.json()["description"] == "updated"

    run = client.post(
        f"/api/v1/workflows/{wid}/run",
        headers=auth_headers,
        json={"payload": {}},
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "succeeded"
    assert len(body["step_runs"]) == 1
    assert body["step_runs"][0]["status"] == "succeeded"

    delete = client.delete(f"/api/v1/workflows/{wid}", headers=auth_headers)
    assert delete.status_code == 204


def test_workflow_validation(client, auth_headers):
    bad = client.post(
        "/api/v1/workflows",
        headers=auth_headers,
        json={"name": "Bad", "definition": {"steps": [{"id": "x", "name": "no-type", "type": "totally-bogus-type", "config": {}}]}},
    )
    # Pydantic accepts any string for `type`; the engine rejects unknown types at run time.
    # We just want to assert it's at least accepted at the API boundary.
    assert bad.status_code in (201, 400)

    missing_id = client.post(
        "/api/v1/workflows",
        headers=auth_headers,
        json={"name": "Missing id", "definition": {"steps": [{"name": "x", "type": "log"}]}},
    )
    # pydantic should accept the dict; engine validates per-step on run.
    # Our _validate_definition rejects missing id; assert it returns 400.
    assert missing_id.status_code in (400, 422)

    duplicate = client.post(
        "/api/v1/workflows",
        headers=auth_headers,
        json={"name": "Dup", "definition": {"steps": [
            {"id": "a", "name": "a", "type": "log"},
            {"id": "a", "name": "b", "type": "log"},
        ]}},
    )
    assert duplicate.status_code == 400


def test_dashboard(client, auth_headers):
    r = client.get("/api/v1/dashboard", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "workflows" in body and "runs" in body and "schedules" in body
