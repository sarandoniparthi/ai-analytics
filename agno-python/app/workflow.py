import json
import os
import re
from typing import Any

from .openrouter_client import call_openrouter_message

AGNO_AVAILABLE = False
Agent = None
OpenAILike = None
OpenAIChat = None
OpenRouter = None

try:
    from agno.agent import Agent as _Agent

    Agent = _Agent
    AGNO_AVAILABLE = True
except Exception:
    AGNO_AVAILABLE = False

if AGNO_AVAILABLE:
    try:
        from agno.models.openrouter import OpenRouter as _OpenRouter

        OpenRouter = _OpenRouter
    except Exception:
        OpenRouter = None

if AGNO_AVAILABLE:
    try:
        from agno.models.openai.like import OpenAILike as _OpenAILike

        OpenAILike = _OpenAILike
    except Exception:
        OpenAILike = None

if AGNO_AVAILABLE:
    try:
        from agno.models.openai import OpenAIChat as _OpenAIChat

        OpenAIChat = _OpenAIChat
    except Exception:
        OpenAIChat = None


def _extract_agent_text(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result.strip()
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content.strip()
    messages = getattr(result, "messages", None)
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            text = last.get("content")
            if isinstance(text, str):
                return text.strip()
    return str(result).strip()


def _parse_sql_from_llm(content: str) -> str | None:
    text = content.strip()
    if not text:
        return None
    try:
        if text.startswith("{"):
            payload = json.loads(text)
            query = payload.get("query")
            if isinstance(query, str) and query.strip():
                return query.strip()
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"\{[\s\S]*\}", text)
    if fenced_match:
        try:
            payload = json.loads(fenced_match.group(0))
            query = payload.get("query")
            if isinstance(query, str) and query.strip():
                return query.strip()
        except json.JSONDecodeError:
            return None
    return None


def _parse_sql_payload(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if not text:
        return None
    candidates: list[dict[str, Any]] = []
    try:
        if text.startswith("{"):
            payload = json.loads(text)
            if isinstance(payload, dict):
                candidates.append(payload)
    except json.JSONDecodeError:
        pass
    fenced_match = re.search(r"\{[\s\S]*\}", text)
    if fenced_match:
        try:
            payload = json.loads(fenced_match.group(0))
            if isinstance(payload, dict):
                candidates.append(payload)
        except json.JSONDecodeError:
            pass
    for payload in candidates:
        query = payload.get("query")
        if isinstance(query, str) and query.strip():
            return {
                "query": query.strip(),
                "explain": str(payload.get("explain", "")),
                "risk": str(payload.get("risk", "med")).lower(),
            }
    return None


def _build_agno_agent(name: str, instructions: str, model_id: str | None = None):
    if not AGNO_AVAILABLE:
        raise RuntimeError("Agno framework is not installed or import failed.")
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for Agno agent execution.")
    model = model_id or os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if OpenRouter is not None:
        agent_model = OpenRouter(
            id=model,
            api_key=api_key,
            base_url=base_url,
        )
    elif OpenAILike is not None:
        agent_model = OpenAILike(
            id=model,
            api_key=api_key,
            base_url=base_url,
        )
    elif OpenAIChat is not None:
        agent_model = OpenAIChat(
            id=model,
            api_key=api_key,
            base_url=base_url,
        )
    else:
        raise RuntimeError("No compatible Agno OpenAI-compatible model class found.")

    return Agent(
        name=name,
        model=agent_model,
        instructions=instructions,
        markdown=False,
    )


class SchemaRagAgent:
    def __init__(self) -> None:
        self.agent = None

    def run(self, rag_docs: list[dict[str, Any]]) -> str:
        if not rag_docs:
            return "No RAG context documents available."
        raw_context = "\n".join(
            [f"- [{d.get('doc_type','doc')}] {d.get('source','unknown')}: {d.get('content','')[:300]}" for d in rag_docs]
        )
        return raw_context


class SQLAgent:
    def __init__(self) -> None:
        self.last_model_used: str | None = None

    def _model_candidates(self, primary: str) -> list[str]:
        fallback_raw = os.getenv("OPENROUTER_FALLBACK_MODELS", "")
        fallback = [m.strip() for m in fallback_raw.split(",") if m.strip()]
        ordered = [primary] + fallback
        unique: list[str] = []
        for model_name in ordered:
            if model_name not in unique:
                unique.append(model_name)
        return unique

    def run(
        self,
        question: str,
        allowed_views: list[str],
        rag_context: str,
        model: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        semantic_hints = []
        q = question.lower()
        if ("top 10 customers" in q or "top customers" in q) and "v_payment_scoped" in [v.lower() for v in allowed_views]:
            semantic_hints.append(
                "For top customers intent, use: "
                "SELECT customer_id, SUM(amount) AS total_amount "
                "FROM v_payment_scoped GROUP BY customer_id "
                "ORDER BY total_amount DESC LIMIT 10"
            )
        allowed_lower = [v.lower() for v in allowed_views]
        if ("rental count by name" in q or "rentals by name" in q) and (
            "v_rental_scoped" in allowed_lower and "v_customer_masked" in allowed_lower
        ):
            semantic_hints.append(
                "For rental count by name, use: "
                "SELECT c.first_name_masked, c.last_name_masked, COUNT(*) AS rental_count "
                "FROM v_rental_scoped r "
                "JOIN v_customer_masked c ON c.customer_id = r.customer_id "
                "GROUP BY c.first_name_masked, c.last_name_masked "
                "ORDER BY rental_count DESC LIMIT 20"
            )

        prompt = (
            f"Question: {question}\n"
            f"Allowed views: {', '.join(allowed_views) or 'none'}\n"
            f"RAG context:\n{rag_context}\n"
            f"Semantic hints:\n{chr(10).join(semantic_hints) if semantic_hints else 'none'}\n"
            "Rules: single SELECT/CTE only, no DDL/DML, include LIMIT <= 200.\n"
            "Return JSON only: {\"query\":\"...\",\"explain\":\"...\",\"risk\":\"low|med|high\"}."
        )

        errors: list[str] = []
        attempts: list[dict[str, Any]] = []
        for model_name in self._model_candidates(model):
            try:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You generate one safe Postgres query. "
                            "Return JSON only: {\"query\":\"...\"}. "
                            "Use only allowed views, SELECT/CTE only, single statement."
                        ),
                    }
                ]
                if conversation_history:
                    messages.extend(conversation_history)
                messages.append({"role": "user", "content": prompt})
                result = call_openrouter_message(messages, model=model_name, reasoning_enabled=True)
                raw_text = str(result.get("content", ""))
                reasoning_details = result.get("reasoning_details")
                provider_model = str(result.get("model", model_name))
                usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
                provider_response_id = str(result.get("provider_response_id", "") or "")

                parsed_payload = _parse_sql_payload(raw_text)
                if parsed_payload:
                    self.last_model_used = model_name
                    attempts.append({"model": model_name, "status": "ok"})
                    assistant_artifact = {
                        "content": raw_text,
                        "reasoning_details": reasoning_details,
                        "model": provider_model,
                        "prompt": prompt,
                        "usage": usage,
                        "provider_response_id": provider_response_id,
                        "model_attempts": attempts,
                    }
                    return parsed_payload, assistant_artifact
                lower = raw_text.lower()
                if "429" in lower or "rate limit" in lower or "rate-limited" in lower:
                    attempts.append({"model": model_name, "status": "rate_limit"})
                    errors.append(f"{model_name}: rate_limit")
                    continue
                if "402" in lower or "payment required" in lower or "spend limit" in lower:
                    attempts.append({"model": model_name, "status": "billing_limit"})
                    errors.append(f"{model_name}: billing_limit")
                    continue
                if not raw_text.strip():
                    attempts.append({"model": model_name, "status": "provider_error_empty"})
                    errors.append(f"{model_name}: provider_error_empty")
                    continue
                attempts.append({"model": model_name, "status": "provider_error_invalid_payload"})
                errors.append(f"{model_name}: provider_error_invalid_payload")
            except Exception as exc:
                msg = str(exc).lower()
                if "429" in msg or "rate limit" in msg or "rate-limited" in msg:
                    attempts.append({"model": model_name, "status": "rate_limit"})
                    errors.append(f"{model_name}: rate_limit")
                    continue
                if "402" in msg or "payment required" in msg or "spend limit" in msg:
                    attempts.append({"model": model_name, "status": "billing_limit"})
                    errors.append(f"{model_name}: billing_limit")
                    continue
                attempts.append({"model": model_name, "status": "provider_error"})
                errors.append(f"{model_name}: provider_error")

        raise RuntimeError(f"all_models_failed: {'; '.join(errors)}")


class Validator:
    def __init__(self) -> None:
        self.agent = None

    def run(self, query: str) -> str:
        return query


class InsightAgent:
    def __init__(self) -> None:
        self.agent = None

    def run(self, rows: list[tuple[Any, ...]], columns: list[str]) -> str:
        if not rows:
            return "No rows returned."
        if len(rows) == 1 and len(rows[0]) == 1:
            label = columns[0] if columns else "value"
            return f"{label}: {rows[0][0]}"
        return f"Returned {len(rows)} rows."


class NarratorAgent:
    def __init__(self) -> None:
        self.agent = None
        try:
            self.agent = _build_agno_agent(
                name="NarratorAgent",
                instructions="Rewrite analytics answers concisely and clearly in plain text.",
            )
        except Exception:
            self.agent = None

    def run(self, answer: str, question: str) -> str:
        if self.agent is not None:
            try:
                result = self.agent.run(f"Question: {question}\nDraft answer: {answer}\nReturn concise plain text only.")
                text = _extract_agent_text(result)
                if text:
                    return text
            except Exception:
                pass
        if answer.startswith("Returned"):
            return f"For '{question}', {answer.lower()}."
        return answer


class KnowledgeAgent:
    def run(self, rag_docs: list[dict[str, Any]]) -> str:
        if not rag_docs:
            return "No knowledge docs found."
        return "\n".join(
            [f"[{d.get('doc_type','doc')}] {d.get('source','unknown')}: {d.get('content','')[:280]}" for d in rag_docs]
        )


class PlannerAgent:
    def run(self, question: str) -> dict[str, Any]:
        q = question.lower()
        intent = "kpi"
        if "trend" in q or "daily" in q or "over time" in q:
            intent = "trend"
        elif "top" in q or "rank" in q:
            intent = "ranking"
        elif "distribution" in q or "share" in q:
            intent = "distribution"
        elif "compare" in q or "vs" in q:
            intent = "comparison"
        widgets = ["table", "metric_card"]
        if intent in {"trend", "ranking", "distribution", "comparison"}:
            widgets.append("bar")
        return {"intent": intent, "widgets": widgets}


class DBTool:
    def run(self, query: str) -> str:
        return query


class WidgetAgent:
    def run(self) -> dict[str, Any]:
        return {"ok": True}
