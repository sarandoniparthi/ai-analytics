import hashlib
import json
import math
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg2


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=_json_default)


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "pagila"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


def execute_query(query: str) -> tuple[list[tuple[Any, ...]], list[str]]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description] if cur.description else []
            return rows, columns
    finally:
        conn.close()


def _hash_embedding(text: str, dims: int = 1536) -> list[float]:
    values = [0.0] * dims
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for i, byte in enumerate(digest):
            idx = (byte + i * 31) % dims
            values[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def _to_pgvector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def retrieve_rag_context(question: str, k: int = 5) -> list[dict[str, Any]]:
    embedding = _to_pgvector_literal(_hash_embedding(question))
    sql = """
    SELECT id, doc_type, source, content
    FROM rag_documents
    ORDER BY embedding <=> %s::vector
    LIMIT %s
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (embedding, k))
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "doc_type": row[1],
                    "source": row[2],
                    "content": row[3],
                }
                for row in rows
            ]
    except psycopg2.Error:
        return []
    finally:
        conn.close()


def create_query_audit_log(
    conversation_id: str,
    org_id: str,
    user_id: str,
    correlation_id: str,
    question: str,
    role: str,
    store_id: int,
    allowed_views: list[str],
) -> int | None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO query_audit_logs
                (conversation_id, org_id, user_id, correlation_id, question, role, store_id, allowed_views, status, error_stage)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'received', 'init')
                RETURNING id
                """,
                (
                    conversation_id,
                    org_id,
                    user_id,
                    correlation_id,
                    question,
                    role,
                    store_id,
                    _json_dumps(allowed_views),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row else None
    except psycopg2.Error:
        conn.rollback()
        return None
    finally:
        conn.close()


def update_query_audit_log(
    log_id: int | None,
    *,
    status: str | None = None,
    error_stage: str | None = None,
    error_message: str | None = None,
    llm_model: str | None = None,
    llm_prompt: str | None = None,
    llm_response: str | None = None,
    generated_sql: str | None = None,
    final_answer: str | None = None,
    rows_count: int | None = None,
    exec_ms: int | None = None,
    rag_sources: list[str] | None = None,
    rag_doc_ids: list[int] | None = None,
    widgets: list[dict[str, Any]] | None = None,
    final_response: dict[str, Any] | None = None,
    llm_usage: dict[str, Any] | None = None,
    model_attempts: list[dict[str, Any]] | None = None,
    error_code: str | None = None,
    llm_input_tokens: int | None = None,
    llm_output_tokens: int | None = None,
    llm_total_tokens: int | None = None,
    llm_cost_usd: float | None = None,
    started_at_now: bool = False,
    completed_at_now: bool = False,
    rag_ms: int | None = None,
    llm_ms: int | None = None,
    validation_ms: int | None = None,
    total_ms: int | None = None,
) -> None:
    if not log_id:
        return

    updates: list[str] = []
    params: list[Any] = []
    if status is not None:
        updates.append("status = %s")
        params.append(status)
    if error_stage is not None:
        updates.append("error_stage = %s")
        params.append(error_stage)
    if error_message is not None:
        updates.append("error_message = %s")
        params.append(error_message[:4000])
    if llm_model is not None:
        updates.append("llm_model = %s")
        params.append(llm_model)
    if llm_prompt is not None:
        updates.append("llm_prompt = %s")
        params.append(llm_prompt)
    if llm_response is not None:
        updates.append("llm_response = %s")
        params.append(llm_response)
    if generated_sql is not None:
        updates.append("generated_sql = %s")
        params.append(generated_sql)
    if final_answer is not None:
        updates.append("final_answer = %s")
        params.append(final_answer)
    if rows_count is not None:
        updates.append("rows_count = %s")
        params.append(rows_count)
    if exec_ms is not None:
        updates.append("exec_ms = %s")
        params.append(exec_ms)
    if rag_sources is not None:
        updates.append("rag_sources = %s::jsonb")
        params.append(_json_dumps(rag_sources))
    if rag_doc_ids is not None:
        updates.append("rag_doc_ids = %s::jsonb")
        params.append(_json_dumps(rag_doc_ids))
    if widgets is not None:
        updates.append("widgets = %s::jsonb")
        params.append(_json_dumps(widgets))
    if final_response is not None:
        updates.append("final_response = %s::jsonb")
        params.append(_json_dumps(final_response))
    if llm_usage is not None:
        updates.append("llm_usage = %s::jsonb")
        params.append(_json_dumps(llm_usage))
    if model_attempts is not None:
        updates.append("model_attempts = %s::jsonb")
        params.append(_json_dumps(model_attempts))
    if error_code is not None:
        updates.append("error_code = %s")
        params.append(error_code)
    if llm_input_tokens is not None:
        updates.append("llm_input_tokens = %s")
        params.append(llm_input_tokens)
    if llm_output_tokens is not None:
        updates.append("llm_output_tokens = %s")
        params.append(llm_output_tokens)
    if llm_total_tokens is not None:
        updates.append("llm_total_tokens = %s")
        params.append(llm_total_tokens)
    if llm_cost_usd is not None:
        updates.append("llm_cost_usd = %s")
        params.append(llm_cost_usd)
    if started_at_now:
        updates.append("started_at = NOW()")
    if completed_at_now:
        updates.append("completed_at = NOW()")
    if rag_ms is not None:
        updates.append("rag_ms = %s")
        params.append(rag_ms)
    if llm_ms is not None:
        updates.append("llm_ms = %s")
        params.append(llm_ms)
    if validation_ms is not None:
        updates.append("validation_ms = %s")
        params.append(validation_ms)
    if total_ms is not None:
        updates.append("total_ms = %s")
        params.append(total_ms)
    updates.append("updated_at = NOW()")

    if not updates:
        return

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE query_audit_logs SET {', '.join(updates)} WHERE id = %s",
                [*params, log_id],
            )
            conn.commit()
    except psycopg2.Error:
        conn.rollback()
    finally:
        conn.close()


def add_query_audit_event(
    log_id: int | None,
    stage: str,
    status: str,
    message: str = "",
    duration_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not log_id:
        return
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO query_audit_events
                (log_id, stage, status, message, duration_ms, metadata)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    log_id,
                    stage,
                    status,
                    message[:2000],
                    duration_ms,
                    _json_dumps(metadata or {}),
                ),
            )
            conn.commit()
    except psycopg2.Error:
        conn.rollback()
    finally:
        conn.close()
