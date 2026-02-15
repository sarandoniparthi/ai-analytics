# backend-nestjs

Public API gateway for UI -> internal Agno.

## Auth Endpoint

`POST /api/auth/login`

Request:
```json
{
  "username": "manager_store1",
  "password": "manager123"
}
```

Response:
- `token` (JWT)
- `user` (role + store access)

## Endpoint

`POST /api/ask`

Request:
```json
{
  "question": "count payments",
  "role": "finance",
  "store_id": 1
}
```

Header:
- `Authorization: Bearer <jwt>`

Backend takes these from JWT claims (overrides body):
- `role`
- `store_id`
- `user_id` (or `sub`)
- `store_ids`
- `is_all_stores`

Current behavior:
- `org_id` uses backend default (`default-org`) until tenant mapping is added.

Required env for JWT mode:
- `JWT_SECRET`

Role to allowed views:
- `admin` -> `v_payment_scoped`, `v_customer_masked`, `v_rental_scoped`
- `store_manager` -> `v_payment_scoped`, `v_rental_scoped`
- `marketing` -> `v_customer_masked`
- `finance` -> `v_payment_scoped`

Behavior:
- Creates `conversation_id` UUID
- Calls internal `AGNO_URL/run`
- Adds header `X-Internal-Token`
- Timeout: `AGNO_TIMEOUT_MS` (default 45s), retry: 1 for retryable failures
