# AI Analytics Copilot

Minimal analytics copilot stack with role-scoped querying:
- `frontend-nextjs` (UI): `http://localhost:3001`
- `backend-nestjs` (API): `http://localhost:3000`
- `agno-python` (internal-only service)
- `postgres` (`pgvector/pgvector:pg16`) on `localhost:5433`

## Database Diagram

- Extended ER diagram: `DB_ERD.md`
- Combined flow + ER diagrams: `ARCHITECTURE_DIAGRAMS.md`

## 1) Start

```bash
docker compose up -d --build
```

## 2) Download Pagila Files

Download into repo root:
- `pagila-schema.sql`
- `pagila-data.sql`

Source:
`https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/pagila/pagila/`

## 3) Import Pagila (PowerShell)

```powershell
Get-Content .\pagila-schema.sql | docker compose exec -T postgres psql -U postgres -d pagila
Get-Content .\pagila-data.sql | docker compose exec -T postgres psql -U postgres -d pagila
```

## 4) Apply Project SQL (PowerShell)

```powershell
Get-Content .\agno-python\sql\001_rag.sql | docker compose exec -T postgres psql -U postgres -d pagila
Get-Content .\agno-python\sql\002_seed_rag.sql | docker compose exec -T postgres psql -U postgres -d pagila
Get-Content .\agno-python\sql\002_scoped_views.sql | docker compose exec -T postgres psql -U postgres -d pagila
Get-Content .\agno-python\sql\003_query_audit_logs.sql | docker compose exec -T postgres psql -U postgres -d pagila
Get-Content .\agno-python\sql\004_query_audit_enhancements.sql | docker compose exec -T postgres psql -U postgres -d pagila
Get-Content .\agno-python\sql\005_auth_users_roles.sql | docker compose exec -T postgres psql -U postgres -d pagila
```

## 5) Verify

```powershell
docker compose exec -T postgres psql -U postgres -d pagila -c "SELECT COUNT(*) FROM payment;"
docker compose exec -T postgres psql -U postgres -d pagila -c "SELECT COUNT(*) FROM rag_documents;"
docker compose exec -T postgres psql -U postgres -d pagila -c "SELECT store_id, COUNT(*), ROUND(SUM(amount)::numeric,2) FROM v_payment_scoped GROUP BY store_id ORDER BY store_id;"
docker compose exec -T postgres psql -U postgres -d pagila -c "SELECT id, conversation_id, status, error_stage, created_at FROM query_audit_logs ORDER BY id DESC LIMIT 10;"
docker compose exec -T postgres psql -U postgres -d pagila -c "SELECT id, log_id, stage, status, duration_ms, created_at FROM query_audit_events ORDER BY id DESC LIMIT 20;"
```

## 5.1) Backend Smoke Tests

Run from `backend-nestjs`:

```powershell
npm run test:smoke
```

What is covered:
- Login success (`manager_store1 / manager123`)
- Login failure (wrong password)
- JWT validation failure (invalid token -> `401`)
- Store scope block (`manager_store1` requesting store `2` -> `403`)
- Store scope allow (`manager_multi` can access store `2`)
- Admin scope allow (`admin_user` not blocked by store scope)
- Finance scope block for unassigned store (`finance_user` store `2` -> `403`)

## 6) Use

- UI: `http://localhost:3001`
- API: `POST http://localhost:3000/api/ask`

Example body:
```json
{
  "question": "What is total revenue for my store 1?",
  "role": "store_manager",
  "store_id": 1
}
```

## 7) Login (Simple UI)

Login is available in UI and backend issues JWT on:
- `POST /api/auth/login`

UI behavior:
- First screen is login-only.
- Analytics UI is shown only after successful login.

Seed users from `005_auth_users_roles.sql`:
- `admin_user / admin123` (all stores)
- `manager_store1 / manager123` (store 1)
- `manager_multi / manager123` (stores 1,2)
- `marketing_user / marketing123` (stores 1,2)
- `finance_user / finance123` (store 1)

## OpenRouter Env

Set in `.env`:
```env
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=meta-llama/llama-3.2-3b-instruct:free
OPENROUTER_FALLBACK_MODELS=google/gemma-2-9b-it:free,microsoft/phi-3-mini-128k-instruct:free,qwen/qwen2.5-7b-instruct:free
AGNO_TIMEOUT_MS=45000
AGNO_TELEMETRY=false
AGNO_DISABLE_TELEMETRY=true
PHI_TELEMETRY=false
JWT_SECRET=change-me
```

## JWT-based User Context

Frontend logs in once and stores JWT; each `/api/ask` call forwards:
- `Authorization: Bearer <token>`

Backend verifies token with `JWT_SECRET` and derives these fields from claims (overrides body):
- `role`
- `store_id`
- `user_id` (or `sub`)
- `store_ids` + `is_all_stores` (for store-scope enforcement)

`org_id` is currently defaulted to `default-org` and can be replaced later with tenant mapping tables.

Supported roles:
- `admin`
- `store_manager`
- `marketing`
- `finance`
