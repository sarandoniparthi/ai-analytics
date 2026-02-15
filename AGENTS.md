# Repository Guidelines

## Project Structure & Module Organization
- Root files: `docker-compose.yml`, `docker-compose.dev.yml`, `.env.example`, `README.md`, `AGENTS.md`.
- `frontend-nextjs/`: Next.js App Router UI. Main page is `frontend-nextjs/app/page.tsx`; backend proxy is `frontend-nextjs/app/api/ask/route.ts`.
- `backend-nestjs/`: NestJS gateway with main endpoint in `backend-nestjs/src/chat.controller.ts`.
- `agno-python/`: Internal FastAPI service and workflow (`agno-python/app/main.py`, `agno-python/app/workflow.py`, SQL validator, DB access).
- SQL files are in `agno-python/sql/` (`001_rag.sql`, `002_seed_rag.sql`, `002_scoped_views.sql`, `003_query_audit_logs.sql`, `004_query_audit_enhancements.sql`, `005_auth_users_roles.sql`).

## Build, Test, and Development Commands
- `docker compose up -d --build`: Build and run all services.
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`: Dev mode with bind mounts.
- `docker compose logs -f agno-python backend-nestjs frontend-nextjs`: Tail runtime logs.
- `python -m compileall agno-python/app`: Python syntax check.
- `Get-Content .\agno-python\sql\001_rag.sql | docker compose exec -T postgres psql -U postgres -d pagila`: Apply migrations from PowerShell.

## Coding Style & Naming Conventions
- TypeScript: strict mode, `camelCase` variables/functions, `PascalCase` classes/DTOs.
- Python: PEP 8, snake_case, explicit typing on core interfaces.
- Keep modules small and single-purpose; avoid adding cross-layer coupling.

## Testing Guidelines
- No committed unit test suite yet; use integration smoke checks.
- Required verification:
  1. `docker compose up -d --build` starts all services.
  2. `POST /api/ask` returns structured payload.
  3. SQL validator blocks unsafe statements.

## Commit & Pull Request Guidelines
- Use Conventional Commits (for example: `feat: add role mapping`, `fix: tighten sql validation`).
- PRs should include scope, env/config changes, commands run, and sample request/response.

## Security & Configuration Tips
- Never commit real secrets (`OPENROUTER_API_KEY`, tokens).
- Keep `agno-python` internal-only (no host port mapping).
- Enforce `X-Internal-Token` on every `/run` call.
