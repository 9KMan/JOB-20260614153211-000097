# FlowForge

> **AI Workflow Automation for holding companies** — REST + webhook + cron triggers, pluggable step runners (HTTP · AI · email · Slack · transforms), append-only audit log, and a flat-design dashboard.

FlowForge is a self-hostable workflow automation platform designed for the messy reality of multi-business groups: many CRMs, ERPs, inboxes, and databases, none of which talk to each other by default. It gives an internal ops team a single place to model, run, observe, and audit business workflows, with first-class support for LLM-powered steps.

This repository is a working public PoC: clone, `pip install -r flowforge/requirements.txt`, `python -m flowforge.scripts.seed`, and you have a runnable system in under a minute.

---

## Highlights

| Layer | Built |
| --- | --- |
| Workflow engine | DAG-of-steps, pluggable handlers, per-step timeout, per-run trace, audit log on every state change |
| Triggers | manual · cron (5- or 6-field) · webhook · etl |
| Step types | `http` · `ai` · `email` · `slack` · `transform` (JMESPath) · `condition` · `delay` · `log` |
| LLM provider | Pluggable: `stub` (offline, deterministic) · `openai` · `anthropic` |
| ETL | JSON / CSV / HTTP / inline; rename + pick transforms |
| Auth | JWT (HS256) with bcrypt password hashing |
| Audit | Append-only `audit_log` for every mutation |
| UI | Flat-design SPA, plain HTML + Tailwind + vanilla JS — no build step |
| Tests | 17 passing, covering API, engine, ETL, LLM stub |
| Deployment | Single-process FastAPI + uvicorn, or docker-compose with Postgres |

---

## Quick start

```bash
# 1. Create venv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -r flowforge/requirements.txt

# 2. Seed a demo user, integrations, agent, and 2 workflows
PYTHONPATH=. python -m flowforge.scripts.seed

# 3. Run the server
PYTHONPATH=. python -m uvicorn flowforge.api.main:app --reload --port 8000

# 4. Open
#    http://localhost:8000           (dashboard, login: demo@flowforge.example / flowforge-demo)
#    http://localhost:8000/docs      (OpenAPI explorer)
#    http://localhost:8000/redoc     (alternative docs)
```

### Docker

```bash
docker compose up --build
# then open http://localhost:8000
```

The compose file ships a Postgres service. Override `DATABASE_URL` to use any
other database. For local dev, the default SQLite database (`flowforge.db`) is
created automatically on first boot.

---

## Architecture

```
flowforge/
├── api/                FastAPI routes (auth, workflows, runs, integrations, agents, etl, dashboard, public)
├── core/               config, database, security, logging
├── models/             SQLAlchemy 2.0 ORM models
├── services/
│   ├── workflow_engine.py   synchronous execution loop
│   ├── step_runner.py       pluggable step handlers + step-type catalog
│   ├── llm.py               stub / openai / anthropic adapters
│   ├── scheduler.py         APScheduler wrapper for cron triggers
│   ├── etl.py               source fetchers (inline/json/csv/http) + transforms
│   └── audit.py             append-only audit log helper
├── workers/runner.py    placeholder long-running worker (scheduler runs in-process today)
├── frontend/            HTML + Tailwind + vanilla JS dashboard
├── scripts/seed.py      demo data
└── tests/               pytest suite (17 tests)
```

### Workflow definition

A workflow is a JSON object with an ordered list of `steps`. Each step has
`id`, `name`, `type`, and `config`. Step outputs are stored under
`state.steps.<step-id>` and can be referenced from later steps with
`${{ steps.<step-id>.<path> }}` interpolation (JMESPath under the hood).

```json
{
  "name": "Daily Lead Enrichment",
  "trigger": "schedule",
  "schedule": "0 9 * * 1-5",
  "definition": {
    "steps": [
      {
        "id": "fetch",
        "name": "Fetch leads from CRM",
        "type": "http",
        "config": {
          "method": "GET",
          "url": "https://crm.example.com/api/leads",
          "integration": "crm-api"
        }
      },
      {
        "id": "summarize",
        "name": "Summarize with AI",
        "type": "ai",
        "config": {
          "prompt": "Summarize these leads in 3 bullets: ${{ steps.fetch.json }}",
          "system": "Be precise, no fluff.",
          "temperature": 0.1,
          "provider": "openai"
        }
      },
      {
        "id": "notify",
        "name": "Post summary to Slack",
        "type": "slack",
        "config": {
          "text": "Daily summary ready: ${{ steps.summarize.text | default('(no summary)') }}",
          "integration": "slack-default"
        }
      }
    ]
  }
}
```

### Triggers

| Trigger | How to fire | Notes |
| --- | --- | --- |
| `manual` | `POST /api/v1/workflows/{id}/run` (auth) | from dashboard or any client |
| `schedule` | cron expression in `workflow.schedule` | re-hydrated on every startup |
| `webhook` | `POST /api/v1/public/webhook/{id}` (no auth) | URL itself acts as a shared secret; swap for HMAC signing in production |
| `etl` | `POST /api/v1/etl/run` then chain into a workflow | first-class ETL endpoint with source/transform |

### Step types

| Type | Purpose | Key config |
| --- | --- | --- |
| `http` | call any HTTP endpoint | `method`, `url`, `headers`, `params`, `body`, `timeout`, `integration` |
| `ai` | call the LLM provider | `prompt`, `system`, `temperature`, `model`, `provider` |
| `email` | send via SMTP | `to`, `subject`, `body`, `integration` (falls back to preview if SMTP unset) |
| `slack` | post to Slack incoming webhook | `text`, `integration` |
| `transform` | extract a value with JMESPath, optionally store at `path` | `expression`, `path` |
| `condition` | compare two values; branch or stop | `left`, `op`, `right`, `branch` |
| `delay` | wait N seconds (max 30) | `seconds` |
| `log` | record a log line in run output | `message`, `level` |

`op` accepts: `==`, `!=`, `>`, `<`, `>=`, `<=`, `contains`, `in`.

### LLM provider

Set `LLM_PROVIDER=stub` (default — offline, deterministic) for development, or
`openai` / `anthropic` with `LLM_API_KEY` for real models. Per-step overrides
work via `provider` and `model` in step config.

The stub provider echoes the prompt with a SHA-256 fingerprint, so you can
verify routing and templating without paying for tokens:

```
[stub:stub-1] c24fb749 :: Summarize these leads in 3 bullets
```

### API surface (v1)

| Method · Path | Purpose |
| --- | --- |
| `POST /api/v1/auth/register` · `POST /api/v1/auth/login` · `GET /api/v1/auth/me` | authentication |
| `GET/POST /api/v1/workflows` · `GET/PATCH/DELETE /api/v1/workflows/{id}` | workflow CRUD |
| `POST /api/v1/workflows/{id}/run` | manual trigger |
| `GET /api/v1/workflows/{id}/runs` | run history for one workflow |
| `POST /api/v1/workflows/{id}/webhook` | authenticated webhook |
| `GET /api/v1/runs` · `GET /api/v1/runs/{id}` | run history (cross-workflow) |
| `GET/POST /api/v1/integrations` · `GET/DELETE /api/v1/integrations/{id}` | integration CRUD (secrets are write-only) |
| `GET/POST /api/v1/agents` · `POST /api/v1/agents/complete` · `GET /api/v1/agents/_catalog/models` | agent CRUD + LLM playground |
| `POST /api/v1/etl/run` · `POST /api/v1/etl/dry-run` | ETL runner |
| `GET /api/v1/schedules` · `GET /api/v1/audit` · `GET /api/v1/dashboard` | ops surface |
| `GET /api/v1/catalog/step-types` | live catalog of step types + their config schema |
| `POST /api/v1/public/webhook/{id}` | unauthenticated webhook |
| `GET /healthz` | health probe |
| `GET /docs` · `GET /redoc` | OpenAPI / ReDoc |

### Security notes

- JWTs are signed with HS256 by default. **Set `JWT_SECRET` to a 32+ byte
  random value in production** (and rotate it).
- Integration `secret` payloads are never echoed back via the API — only a
  per-field `set` / `********` mask is returned.
- All write endpoints (mutations) write an `audit_log` entry referencing the
  actor, target, and a small payload.
- The public webhook trusts the URL — fine for internal networks; for
  internet exposure, switch to HMAC-signed webhooks.
- All queries are parameterized via SQLAlchemy 2.0.
- Step output is JSON-serializable only — never echo raw binary into state.

---

## Running the test suite

```bash
PYTHONPATH=. python -m pytest flowforge/tests -v
```

Covers API auth + CRUD, workflow engine (log, condition, AI stub, unknown
type), ETL (inline / json / csv), and LLM stub determinism. 17 tests pass in
under 10 seconds on a cold venv.

---

## Environment variables

| Name | Default | Notes |
| --- | --- | --- |
| `APP_NAME` | `FlowForge` | |
| `ENV` | `development` | |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | |
| `DATABASE_URL` | `sqlite:///./flowforge.db` | swap to `postgresql+psycopg://…` for prod |
| `JWT_SECRET` | dev placeholder | **must** be replaced in production |
| `JWT_EXPIRATION_MINUTES` | `480` (8h) | |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:8000` | comma-separated |
| `LLM_PROVIDER` | `stub` | `stub` · `openai` · `anthropic` |
| `LLM_API_KEY` | empty | required for `openai` / `anthropic` |
| `LLM_DEFAULT_MODEL` · `LLM_OPENAI_MODEL` · `LLM_ANTHROPIC_MODEL` | provider-specific | |
| `STEP_TIMEOUT_SECONDS` | `60` | per-step timeout |
| `SMTP_HOST` · `SMTP_PORT` · `SMTP_USER` · `SMTP_PASSWORD` · `SMTP_FROM` | empty | used when an `email` step has no integration |
| `SLACK_WEBHOOK_URL` | empty | fallback Slack webhook |
| `AUDIT_LOG_RETENTION_DAYS` | `90` | (future) audit-log retention hint |

---

## Project layout (high level)

```
.
├── flowforge/
│   ├── api/                  FastAPI routes + schemas
│   ├── core/                 config, db, security, logging
│   ├── models/               SQLAlchemy 2.0 ORM models (User, Workflow, Run, StepRun, Integration, Agent, AuditLog)
│   ├── services/             workflow engine, step runner, LLM, scheduler, ETL, audit
│   ├── workers/              long-running worker process (cron hydrator)
│   ├── frontend/             static dashboard
│   ├── scripts/seed.py       demo data
│   ├── tests/                pytest suite
│   ├── __main__.py           `python -m flowforge`
│   └── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Out of scope (per spec)

- Mobile apps (web only).
- Multi-tenant / white-label.
- Performance tuning for 1M+ user scale.
- Encrypted-at-rest secrets (PoC stores integration secrets in the DB
  unmasked; encrypt before production).

---

## License

MIT (see LICENSE).
