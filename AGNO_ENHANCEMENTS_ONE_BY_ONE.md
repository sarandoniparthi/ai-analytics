# Agno Enhancements: One-by-One Plan

This document is the execution checklist for adding advanced Agno capabilities incrementally without breaking the current stack.

## Current Baseline

- Working flow: UI -> NestJS -> Agno -> Postgres
- JWT role/store scope enforcement
- SQL guardrails and scoped views
- Current PII masking through `v_customer_masked` (`first_name_masked`, `last_name_masked`)
- RAG retrieval from `rag_documents`
- Audit logging (`query_audit_logs`, `query_audit_events`)

## Phase 1: Prompt Packs (Next)

Goal: Runtime prompt customization by org/role/user without code edits.

- Add DB tables:
  - `prompt_pack`
  - `prompt_pack_scope`
  - `prompt_pack_blocks`
- Add backend APIs:
  - `GET /api/prompts/active`
  - `POST /api/prompts`
  - `PUT /api/prompts/:id/blocks`
  - `POST /api/prompts/:id/activate`
  - `POST /api/prompts/:id/archive`
- Agno runtime:
  - merge prompt blocks with precedence: org -> role -> user
  - apply to SQL + narration prompts
- Validation:
  - smoke test for create/activate/fetch active prompt

## Phase 2: Persistent Memory

- Add `agent_memory` table
- Save/load user preferences (answer style, units, common metrics)
- Include memory context in planner/narrator stages

## Phase 3: HITL Approvals

- Add `approval_queue` table
- Guardrail marks high-risk SQL as `pending_approval`
- Add approve/reject backend endpoints

## Phase 4: Policy Engine

- Add policy checks for PII and restricted dimensions
- Add explicit blocklist for sensitive request keywords/columns
- Add response redaction fallback for sensitive column names
- Record policy decisions in audit logs

## Phase 5: Evaluation Loop

- Capture user feedback (thumbs up/down, edited answer)
- Export training dataset JSONL from audit/feedback events

## Phase 6: Model Registry

- Add per-org model registry table
- Runtime model selection with fallback strategy

## Definition of Done (Per Phase)

- DB migration script
- API/service implementation
- Runtime integration
- README update
- Smoke tests added/passing
- Commit and push
