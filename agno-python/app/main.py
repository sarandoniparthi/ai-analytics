import logging
import os
import time
from typing import Any

import psycopg2
from fastapi import FastAPI, Header, HTTPException

from .conversation_memory import ConversationMemory
from .db import (
    add_query_audit_event,
    create_query_audit_log,
    execute_query,
    retrieve_rag_context,
    update_query_audit_log,
)
from .sql_validator import extract_views
from .types import (
    ExplainPayload,
    MetaPayload,
    RunRequest,
    RunResponse,
    SecurityPayload,
    SqlPayload,
)
from .workflow import (
    AgnoAnalyticsWorkflow,
    DBTool,
    WidgetAgent,
)

logger = logging.getLogger("agno-python")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="agno-python")

agno_workflow = AgnoAnalyticsWorkflow()
db_tool = DBTool()
widget_agent = WidgetAgent()
conversation_memory = ConversationMemory(max_messages=8)


def _error_code_from_message(message: str, status_code: int | None = None) -> str:
    lowered = message.lower()
    if status_code == 401:
        return "auth_error"
    if "view not allowed" in lowered:
        return "out_of_scope"
    if "only select/cte" in lowered or "forbidden sql keyword" in lowered:
        return "validation_error"
    if "rate limit" in lowered or "429" in lowered:
        return "rate_limited"
    if "billing" in lowered or "spend limit" in lowered or "402" in lowered:
        return "billing_limit"
    if "database execution failed" in lowered or "relation" in lowered:
        return "db_error"
    if "provider returned error" in lowered or "provider_error" in lowered:
        return "provider_error"
    return "unknown_error"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float))


def _looks_like_date_column(column_name: str) -> bool:
    lowered = column_name.lower()
    return "date" in lowered or lowered in {"day", "month", "year"}


def _widget_preference_from_rag(question: str, rag_docs: list[dict[str, Any]]) -> str | None:
    q = question.lower()
    policy_text = " ".join(
        str(d.get("content", "")).lower() for d in rag_docs if str(d.get("doc_type", "")).lower() == "widget_policy"
    )
    if ("trend" in q or "daily" in q or "over time" in q or "time series" in q) and "line" in policy_text:
        return "line"
    if ("top" in q or "rank" in q or "leaderboard" in q or "compare" in q) and "bar" in policy_text:
        return "bar"
    if ("share" in q or "split" in q or "proportion" in q or "distribution" in q) and "pie" in policy_text:
        return "pie"
    return None


def _question_wants_widget(question: str, widget_type: str) -> bool:
    q = question.lower()
    if widget_type == "pie":
        return "pie chart" in q or "pie" in q or "share" in q or "distribution" in q
    if widget_type == "bar":
        return "bar chart" in q or "bar" in q
    if widget_type == "line":
        return "line chart" in q or "line" in q or "trend" in q
    return False


def build_widgets(
    rows: list[tuple[Any, ...]],
    columns: list[str],
    question: str,
    rag_docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    widgets: list[dict[str, Any]] = []
    if not rows or not columns:
        return widgets

    preferred_widget = _widget_preference_from_rag(question, rag_docs)
    wants_pie = _question_wants_widget(question, "pie")
    wants_bar = _question_wants_widget(question, "bar")
    first_row = rows[0]
    if len(columns) == 1 and len(first_row) == 1:
        metric_name = columns[0]
        metric_value = first_row[0]
        widgets.append(
            {
                "type": "metric_card",
                "title": metric_name,
                "description": "Primary KPI",
                "dataset": {"columns": columns, "rows": [[metric_value]]},
                "config": {"x": metric_name, "y": [metric_name], "series": [], "stack": False, "unit": ""},
            }
        )
        # Fallback chart widgets for single-metric results.
        widgets.append(
            {
                "type": "bar",
                "title": f"{metric_name} (bar)",
                "description": "Single-value bar chart",
                "dataset": {"columns": ["label", metric_name], "rows": [["value", metric_value]]},
                "config": {"x": "label", "y": [metric_name], "series": [], "stack": False, "unit": ""},
            }
        )
        widgets.append(
            {
                "type": "pie",
                "title": f"{metric_name} (pie)",
                "description": "Single-value pie chart",
                "dataset": {"columns": ["label", metric_name], "rows": [["value", metric_value]]},
                "config": {"x": "label", "y": [metric_name], "series": [], "stack": False, "unit": ""},
            }
        )

    if len(columns) >= 2:
        col0 = columns[0]
        col1 = columns[1]
        pairs = []
        for row in rows[:30]:
            if len(row) < 2:
                continue
            if _is_number(row[1]):
                pairs.append({"x": str(row[0]), "y": row[1]})
        if pairs:
            widget_type = preferred_widget or ("line" if _looks_like_date_column(col0) else "bar")
            if wants_pie:
                widget_type = "pie"
            elif wants_bar:
                widget_type = "bar"
            widgets.append(
                {
                    "type": widget_type,
                    "title": f"{col1} by {col0}",
                    "description": "Auto-generated chart",
                    "dataset": {"columns": [col0, col1], "rows": [[p["x"], p["y"]] for p in pairs]},
                    "config": {"x": col0, "y": [col1], "series": [], "stack": False, "unit": ""},
                }
            )
            if widget_type != "pie":
                widgets.append(
                    {
                        "type": "pie",
                        "title": f"{col1} share by {col0}",
                        "description": "Distribution view",
                        "dataset": {"columns": [col0, col1], "rows": [[p["x"], p["y"]] for p in pairs[:12]]},
                        "config": {"x": col0, "y": [col1], "series": [], "stack": False, "unit": ""},
                    }
                )
            if wants_bar and widget_type != "bar":
                widgets.append(
                    {
                        "type": "bar",
                        "title": f"{col1} by {col0}",
                        "description": "Requested bar chart",
                        "dataset": {"columns": [col0, col1], "rows": [[p["x"], p["y"]] for p in pairs[:30]]},
                        "config": {"x": col0, "y": [col1], "series": [], "stack": False, "unit": ""},
                    }
                )
            if wants_pie and widget_type != "pie":
                widgets.append(
                    {
                        "type": "pie",
                        "title": f"{col1} share by {col0}",
                        "description": "Requested pie chart",
                        "dataset": {"columns": [col0, col1], "rows": [[p["x"], p["y"]] for p in pairs[:12]]},
                        "config": {"x": col0, "y": [col1], "series": [], "stack": False, "unit": ""},
                    }
                )

    widgets.append(
        {
            "type": "table",
            "title": "Query Results",
            "description": "Tabular output",
            "dataset": {"columns": columns, "rows": [list(r) for r in rows[:20]]},
            "config": {"x": columns[0] if columns else "", "y": columns[1:2], "series": [], "stack": False, "unit": ""},
        }
    )
    return widgets[:4]


def infer_intent(question: str) -> str:
    q = question.lower()
    if "trend" in q or "daily" in q or "over time" in q:
        return "trend"
    if "top" in q or "rank" in q:
        return "ranking"
    if "share" in q or "distribution" in q:
        return "distribution"
    if "compare" in q or "vs" in q:
        return "comparison"
    return "kpi"


def build_followups(intent: str) -> list[str]:
    if intent == "trend":
        return ["Compare last 30 days vs previous 30 days", "Break trend by store"]
    if intent == "ranking":
        return ["Show top 10 only", "Add store-wise ranking"]
    if intent == "distribution":
        return ["Show percentage split", "Filter by store_id"]
    return ["Show by category", "Compare store 1 vs store 2"]


def build_insights(rows: list[tuple[Any, ...]], columns: list[str]) -> list[str]:
    if not rows:
        return ["No data matched the current scope."]
    if len(rows) == 1 and len(rows[0]) == 1:
        return [f"Primary metric `{columns[0]}` is {rows[0][0]}.", "Result is role-scoped and RLS-safe."]
    return [f"Returned {len(rows)} rows.", f"Columns used: {', '.join(columns)}"]


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse)
def run_query(
    payload: RunRequest,
    x_internal_token: str = Header(default=""),
    x_correlation_id: str = Header(default=""),
) -> RunResponse:
    expected_token = os.getenv("INTERNAL_TOKEN", "")
    default_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
    total_start = time.perf_counter()

    audit_log_id = create_query_audit_log(
        conversation_id=payload.conversation_id,
        org_id=payload.org_id,
        user_id=payload.user_id,
        correlation_id=x_correlation_id,
        question=payload.question,
        role=payload.user_context.role,
        store_id=payload.user_context.store_id,
        allowed_views=payload.user_context.allowed_views,
    )
    update_query_audit_log(audit_log_id, started_at_now=True)

    stage = "auth"
    if not expected_token:
        message = "INTERNAL_TOKEN is not configured."
        update_query_audit_log(
            audit_log_id,
            status="failed",
            error_stage=stage,
            error_code="auth_error",
            error_message=message,
            completed_at_now=True,
            total_ms=int((time.perf_counter() - total_start) * 1000),
        )
        add_query_audit_event(audit_log_id, stage, "failed", message)
        raise HTTPException(status_code=500, detail=message)

    if x_internal_token != expected_token:
        message = "Invalid internal token."
        update_query_audit_log(
            audit_log_id,
            status="failed",
            error_stage=stage,
            error_code="auth_error",
            error_message=message,
            completed_at_now=True,
            total_ms=int((time.perf_counter() - total_start) * 1000),
        )
        add_query_audit_event(audit_log_id, stage, "failed", message)
        raise HTTPException(status_code=401, detail=message)

    add_query_audit_event(audit_log_id, stage, "ok", "Token validated")
    rag_docs: list[dict[str, Any]] = []
    rag_ms = 0
    llm_ms = 0
    validation_ms = 0
    used_model = default_model

    try:
        stage = "rag_retrieval"
        active_model = default_model
        rag_start = time.perf_counter()
        rag_docs = retrieve_rag_context(payload.question, k=5)
        rag_ms = int((time.perf_counter() - rag_start) * 1000)
        add_query_audit_event(
            audit_log_id,
            stage,
            "ok",
            f"Retrieved {len(rag_docs)} docs",
            duration_ms=rag_ms,
        )
        update_query_audit_log(
            audit_log_id,
            status="rag_ready",
            error_stage=stage,
            rag_sources=[str(d.get("source", "")) for d in rag_docs],
            rag_doc_ids=[int(d.get("id")) for d in rag_docs if d.get("id") is not None],
            rag_ms=rag_ms,
        )

        full_context, plan = agno_workflow.build_context_and_plan(payload.question, rag_docs)
        history = conversation_memory.get_messages(payload.conversation_id)
        stage = "llm_generation"
        llm_start = time.perf_counter()
        sql_payload, assistant_artifact = agno_workflow.generate_sql(
            payload.question,
            payload.user_context.allowed_views,
            full_context,
            active_model,
            conversation_history=history,
        )
        llm_ms = int((time.perf_counter() - llm_start) * 1000)
        used_model = agno_workflow.last_model_used or active_model
        llm_usage = assistant_artifact.get("usage") if assistant_artifact else {}
        if not isinstance(llm_usage, dict):
            llm_usage = {}
        update_query_audit_log(
            audit_log_id,
            status="llm_generated",
            error_stage=stage,
            llm_model=used_model,
            llm_prompt=assistant_artifact.get("prompt") if assistant_artifact else payload.question,
            llm_response=assistant_artifact.get("content") if assistant_artifact else None,
            llm_usage=llm_usage,
            model_attempts=assistant_artifact.get("model_attempts") if assistant_artifact else None,
            llm_input_tokens=int(llm_usage.get("prompt_tokens", 0) or 0),
            llm_output_tokens=int(llm_usage.get("completion_tokens", 0) or 0),
            llm_total_tokens=int(llm_usage.get("total_tokens", 0) or 0),
            llm_ms=llm_ms,
        )
        add_query_audit_event(
            audit_log_id,
            stage,
            "ok",
            f"Generated SQL candidate with model {used_model}",
            duration_ms=llm_ms,
        )

        if assistant_artifact:
            conversation_memory.append_exchange(
                conversation_id=payload.conversation_id,
                user_content=assistant_artifact.get("prompt", payload.question),
                assistant_content=assistant_artifact.get("content", ""),
                reasoning_details=assistant_artifact.get("reasoning_details"),
            )

        stage = "validation"
        validation_start = time.perf_counter()
        executable_sql, views_used = agno_workflow.validate_sql(sql_payload, payload.user_context.allowed_views)
        validation_ms = int((time.perf_counter() - validation_start) * 1000)
        update_query_audit_log(
            audit_log_id,
            status="validated",
            error_stage=stage,
            generated_sql=executable_sql,
            validation_ms=validation_ms,
        )
        add_query_audit_event(audit_log_id, stage, "ok", "SQL validated", duration_ms=validation_ms)

    except Exception as exc:
        if isinstance(exc, HTTPException):
            detail = str(exc.detail)
            update_query_audit_log(
                audit_log_id,
                status="failed",
                error_stage=stage,
                error_code=_error_code_from_message(detail, exc.status_code),
                error_message=detail,
                completed_at_now=True,
                total_ms=int((time.perf_counter() - total_start) * 1000),
            )
            add_query_audit_event(audit_log_id, stage, "failed", detail)
            raise

        message = str(exc)
        update_query_audit_log(
            audit_log_id,
            status="failed",
            error_stage=stage,
            error_code=_error_code_from_message(message),
            error_message=message,
            completed_at_now=True,
            total_ms=int((time.perf_counter() - total_start) * 1000),
        )
        add_query_audit_event(audit_log_id, stage, "failed", message)
        logger.error(
            "run_agent_error conversation_id=%s role=%s store_id=%s error=%s",
            payload.conversation_id,
            payload.user_context.role,
            payload.user_context.store_id,
            message,
        )
        lowered = message.lower()
        if "all_models_failed" in lowered and "rate_limit" in lowered:
            raise HTTPException(status_code=429, detail="All configured models are rate-limited. Retry shortly.") from exc
        if "all_models_failed" in lowered and "billing_limit" in lowered:
            raise HTTPException(status_code=402, detail="All configured models hit billing/spend limits.") from exc
        if "rate limit" in lowered or "429" in lowered:
            raise HTTPException(status_code=429, detail="LLM rate limited. Retry in a few seconds.") from exc
        if "billing_limit" in lowered or "payment required" in lowered or "402" in lowered or "spend limit" in lowered:
            raise HTTPException(status_code=402, detail="LLM provider spend limit reached. Update OpenRouter key/limits.") from exc
        if "provider_error" in lowered:
            raise HTTPException(status_code=503, detail="LLM provider temporary error. Please retry.") from exc
        raise HTTPException(status_code=500, detail="Agno workflow failed.") from exc

    stage = "db_execution"
    db_start = time.perf_counter()
    try:
        rows, columns = execute_query(db_tool.run(executable_sql))
    except psycopg2.Error as exc:
        message = exc.pgerror or str(exc)
        update_query_audit_log(
            audit_log_id,
            status="failed",
            error_stage=stage,
            generated_sql=executable_sql,
            error_code="db_error",
            error_message=message,
            completed_at_now=True,
            total_ms=int((time.perf_counter() - total_start) * 1000),
        )
        add_query_audit_event(audit_log_id, stage, "failed", message)
        logger.error(
            "run_error conversation_id=%s role=%s store_id=%s sql=%s error=%s",
            payload.conversation_id,
            payload.user_context.role,
            payload.user_context.store_id,
            executable_sql,
            message,
        )
        raise HTTPException(status_code=500, detail="Database execution failed.") from exc

    exec_ms = int((time.perf_counter() - db_start) * 1000)
    add_query_audit_event(audit_log_id, stage, "ok", "SQL executed", duration_ms=exec_ms, metadata={"rows": len(rows)})

    answer = agno_workflow.build_answer(rows, columns, payload.question)
    widgets = build_widgets(rows, columns, payload.question, rag_docs)
    _ = widget_agent.run()

    response_payload = RunResponse(
        conversation_id=payload.conversation_id,
        answer=answer,
        insights=build_insights(rows, columns),
        followups=build_followups(plan["intent"]),
        intent=plan["intent"],
        sql=SqlPayload(query=executable_sql),
        widgets=widgets,
        explain=ExplainPayload(
            views_used=views_used,
            notes="SQL built with RAG context + LLM, then validated by strict safety rules.",
        ),
        security=SecurityPayload(
            role=payload.user_context.role,
            store_id=payload.user_context.store_id,
            rls=True,
            allowed_views=payload.user_context.allowed_views,
        ),
        lineage={"views": views_used, "filters": ["role_scope", "store_scope"]},
        meta=MetaPayload(
            rows=len(rows),
            exec_ms=exec_ms,
            model=used_model,
            confidence="medium",
        ),
    )

    update_query_audit_log(
        audit_log_id,
        status="success",
        error_stage="completed",
        generated_sql=executable_sql,
        final_answer=answer,
        rows_count=len(rows),
        exec_ms=exec_ms,
        llm_model=used_model,
        widgets=widgets,
        final_response=response_payload.model_dump(),
        completed_at_now=True,
        total_ms=int((time.perf_counter() - total_start) * 1000),
    )
    add_query_audit_event(audit_log_id, "completed", "ok", "Request completed successfully")

    logger.info(
        "run_ok conversation_id=%s role=%s store_id=%s sql=%s rows=%s exec_ms=%s views_used=%s",
        payload.conversation_id,
        payload.user_context.role,
        payload.user_context.store_id,
        executable_sql,
        len(rows),
        exec_ms,
        ",".join(extract_views(executable_sql)),
    )

    return response_payload
