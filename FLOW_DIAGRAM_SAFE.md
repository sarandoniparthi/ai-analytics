# Flow Diagram (Safe)

```mermaid
flowchart LR
    U["User in Browser"] --> F["Next.js UI\nfrontend-nextjs/app/page.tsx"]
    F --> P["Next.js API Proxy\n/api/ask"]
    P --> B["NestJS API\nPOST /api/ask"]
    B --> C["Build user_context\nrole + store_id + allowed_views\nconversation_id"]
    C --> A["Agno FastAPI\nPOST /run"]

    A --> T["Validate X-Internal-Token"]
    T --> L0["query_audit_logs\nstatus=received"]

    A --> R["RAG Retrieval\nrag_documents (pgvector)"]
    R --> L1["query_audit_events\nstage=rag_retrieval"]

    R --> M["OpenRouter SQL Generation\nprimary + fallback models"]
    M --> L2["query_audit_events\nstage=llm_generation"]

    M --> V["SQL Validator\nSELECT-only, views-only, LIMIT 200"]
    V --> L3["query_audit_events\nstage=validation"]

    V --> D["Postgres Execute SQL"]
    D --> L4["query_audit_events\nstage=db_execution"]

    D --> W["Build Answer + Widgets\nline/bar/pie/table/metric"]
    W --> L5["query_audit_logs\nfinal_response, status=success/failed"]

    W --> B
    B --> P
    P --> F
    F --> U
```

## PNG Export

Option 1 (`npx`):
```bash
npx -y @mermaid-js/mermaid-cli -i FLOW_DIAGRAM_SAFE.md -o FLOW_DIAGRAM.png
```

Option 2 (Docker):
```bash
docker run --rm -v "$PWD:/data" minlag/mermaid-cli -i /data/FLOW_DIAGRAM_SAFE.md -o /data/FLOW_DIAGRAM.png
```
