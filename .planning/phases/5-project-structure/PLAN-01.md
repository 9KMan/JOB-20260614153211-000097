# Phase 05: Project Structure

## Phase Goal
Establish the directory layout, module boundaries, and file organization.

## Remaining Files
Complete any files not yet created:
- app/services/ (business logic)
- app/worker/ (background tasks)
- API routes for all SPEC endpoints
- Tests (pytest)

## README.md (MANDATORY - byline required)

```file:README.md
# # Specification: Upwork: https://www.upwork.com/jobs/~022065

**Built by: KMan | AI-Augmented Engineering Factory**

## Business Problem Solved
[Extract business problem from SPEC.md - what pain point does this solve? Who benefits? What is the outcome?]

## Quick Start
```
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values
alembic upgrade head
uvicorn app.main:app --reload
```

## Tech Stack
python · node.js · openai api · claude api · n8n · langchain · make · zapier · api integration · crm · erp

## Project Structure
```
app/
  main.py          # FastAPI app
  config.py        # Settings
  database.py      # DB session
  models/          # SQLAlchemy models
  schemas/         # Pydantic schemas
  api/v1/          # API routes
  services/        # Business logic
  worker/          # Background tasks
alembic/           # DB migrations
tests/             # Unit tests
```

## API Overview
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/v1/health | Health check |
| POST | /api/v1/auth/register | Register user |
| POST | /api/v1/auth/login | Login |

## Environment Variables
| Variable | Description |
|----------|-------------|
| DATABASE_URL | PostgreSQL connection string |
| JWT_SECRET | Secret for JWT signing |
| JWT_ALGORITHM | Algorithm (default HS256) |
| JWT_EXPIRE_MINUTES | Access token expiry |
```
