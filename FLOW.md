# End-to-End Flow

## Diagram
- Use `FLOW_DIAGRAM_SAFE.md` for the graphical Mermaid flow (compatibility version + PNG export commands).

## 1) User Request (Frontend)
- User logs in via `POST /api/auth/login` (proxied to backend) and receives JWT.
- User enters `question` in `frontend-nextjs/app/page.tsx`.
- UI calls `POST /api/ask` via `frontend-nextjs/app/api/ask/route.ts`.
- Frontend forwards `Authorization: Bearer <jwt>` on each ask call.

## 2) API Gateway (NestJS)
- Route: `backend-nestjs/src/chat.controller.ts` (`POST /api/ask`).
- Service: `backend-nestjs/src/chat.service.ts`.
- Backend:
  - creates `conversation_id`
  - verifies JWT (`JWT_SECRET`)
  - derives `role`, `store_id`, `user_id`, `store_ids`, `is_all_stores` from JWT claims
  - falls back to request body values if JWT is not provided
  - currently uses default `org_id` (`default-org`)
  - enforces store scope (single or multiple stores based on JWT claims)
  - maps effective role to `allowed_views`
  - sends request to internal Agno:
    - `POST http://agno-python:8000/run`
    - header `X-Internal-Token`

### Conversation ID Storage
- `conversation_id` is generated in `backend-nestjs/src/chat.service.ts`.
- It is returned in API responses and used for request correlation.
- It is persisted in Postgres in `query_audit_logs.conversation_id`.
- Stage-level records are linked through `query_audit_events.log_id` (foreign key to `query_audit_logs.id`).
- It is also used in runtime in-memory stores:
  - Backend in-memory result cache: `backend-nestjs/src/result-store.service.ts`
  - Agno in-memory conversation memory: `agno-python/app/conversation_memory.py`

## 3) Internal Agent Service (Agno/FastAPI)
- Entry: `agno-python/app/main.py` (`POST /run`).
- Validates internal token.
- Retrieves RAG context from `rag_documents` using `retrieve_rag_context()` (`agno-python/app/db.py`).
- Runs SQL generation through workflow (`agno-python/app/workflow.py`) using OpenRouter model + fallback models.

## 4) SQL Safety + Execution
- Validator: `agno-python/app/sql_validator.py`
  - only `SELECT`/`WITH`
  - blocks DDL/DML keywords
  - single statement only
  - enforces `allowed_views`
  - applies `LIMIT 200` if missing
- Executes validated SQL in Postgres via `execute_query()` (`agno-python/app/db.py`).

## 5) Result Packaging
- `agno-python/app/main.py` builds final payload:
  - `answer`
  - `widgets` (`metric_card`, `line`, `bar`, `pie`, `table`)
  - `sql`
  - `explain`
  - `security` (role, store, allowed_views, rls)
  - `meta` (rows, execution time, model)

## 6) Response to UI
- Flow returns: Agno -> NestJS -> Next.js API route -> browser.
- UI renders answer, charts, SQL, explain details, and scope/security panel.

## 7) Audit Logging
- Every `/run` request writes lifecycle data into Postgres:
  - main table: `query_audit_logs`
  - stage events table: `query_audit_events`

### `query_audit_logs` (high-level)
- Request identity/scope:
  - `conversation_id`, `org_id`, `user_id`, `correlation_id`
  - `question`, `role`, `store_id`, `allowed_views`
- RAG trace:
  - `rag_sources`, `rag_doc_ids`, `rag_ms`
- LLM trace:
  - `llm_model`, `llm_prompt`, `llm_response`
  - `llm_usage`, `model_attempts`
  - `llm_input_tokens`, `llm_output_tokens`, `llm_total_tokens`, `llm_cost_usd`, `llm_ms`
- SQL/result trace:
  - `generated_sql`, `rows_count`, `exec_ms`
  - `final_answer`, `widgets`, `final_response`
- Failure/health trace:
  - `status`, `error_stage`, `error_code`, `error_message`
  - `started_at`, `completed_at`, `validation_ms`, `total_ms`, `created_at`, `updated_at`, `expires_at`

### `query_audit_events` (stage timeline)
- One row per stage transition:
  - `log_id`, `stage`, `status`, `message`, `duration_ms`, `metadata`, `created_at`
- Used for step-by-step debugging (for example, where exactly a request failed).
