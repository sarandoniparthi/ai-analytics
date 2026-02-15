# agno-python

Internal FastAPI service for:
- RAG context retrieval (`rag_documents` on pgvector)
- SQL generation with OpenRouter
- SQL safety validation
- Query execution + insight response

This service uses Agno agent classes where compatible model adapters are available.
If a compatible Agno model class is not available in the installed Agno version,
it still calls OpenRouter directly and keeps the same `/run` behavior and safety rules.

## Endpoint

`POST /run` (internal-only)

Header:
- `X-Internal-Token: <INTERNAL_TOKEN>`

Body:
```json
{
  "conversation_id": "uuid",
  "question": "count customers",
  "org_id": "default-org",
  "user_id": "default-user",
  "user_context": {
    "role": "admin",
    "store_id": 1,
    "allowed_views": ["v_payment_scoped", "v_customer_masked"]
  }
}
```

## SQL Rules

- Only single `SELECT` / `WITH ... SELECT`
- Blocks: `INSERT UPDATE DELETE DROP ALTER CREATE GRANT REVOKE TRUNCATE COPY`
- Trailing semicolon only
- Enforces `LIMIT 200` if absent
- Enforces `allowed_views`

## RAG Migration

Run:

```powershell
Get-Content .\sql\001_rag.sql | docker compose exec -T postgres psql -U postgres -d pagila
Get-Content .\sql\002_seed_rag.sql | docker compose exec -T postgres psql -U postgres -d pagila
Get-Content .\sql\002_scoped_views.sql | docker compose exec -T postgres psql -U postgres -d pagila
```
