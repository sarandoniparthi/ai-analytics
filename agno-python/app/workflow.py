import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from .sql_validator import validate_sql

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
    # Normalize different Agno result shapes into a single text payload.
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


def _extract_json_candidates(text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    stripped = text.strip()
    if not stripped:
        return candidates

    try:
        if stripped.startswith("{"):
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                candidates.append(payload)
    except json.JSONDecodeError:
        pass

    # Also scan embedded/fenced JSON blocks in model output.
    for match in re.finditer(r"\{[\s\S]*?\}", stripped):
        raw = match.group(0)
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                candidates.append(payload)
        except json.JSONDecodeError:
            continue

    return candidates


def _parse_sql_payload(content: str) -> dict[str, Any] | None:
    for payload in _extract_json_candidates(content):
        query = payload.get("query")
        if isinstance(query, str) and query.strip():
            return {
                "query": query.strip(),
                "explain": str(payload.get("explain", "")),
                "risk": str(payload.get("risk", "med")).lower(),
            }
    return None


def _parse_intent_payload(content: str) -> str | None:
    for payload in _extract_json_candidates(content):
        intent = payload.get("intent")
        if isinstance(intent, str) and intent.strip():
            normalized = intent.strip().lower()
            if normalized in {"kpi", "trend", "ranking", "distribution", "comparison"}:
                return normalized
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
        agent_model = OpenRouter(id=model, api_key=api_key, base_url=base_url)
    elif OpenAILike is not None:
        agent_model = OpenAILike(id=model, api_key=api_key, base_url=base_url)
    elif OpenAIChat is not None:
        agent_model = OpenAIChat(id=model, api_key=api_key, base_url=base_url)
    else:
        raise RuntimeError("No compatible Agno OpenAI-compatible model class found.")

    return Agent(name=name, model=agent_model, instructions=instructions, markdown=False)


def _heuristic_intent(question: str) -> str:
    q = question.lower()
    if "trend" in q or "daily" in q or "over time" in q:
        return "trend"
    if "top" in q or "rank" in q:
        return "ranking"
    if "distribution" in q or "share" in q:
        return "distribution"
    if "compare" in q or "vs" in q:
        return "comparison"
    return "kpi"


def _widgets_for_intent(intent: str) -> list[str]:
    widgets = ["table", "metric_card"]
    if intent in {"trend", "ranking", "distribution", "comparison"}:
        widgets.append("bar")
    return widgets


def _classify_model_error(message: str) -> str:
    lowered = message.lower()
    if "429" in lowered or "rate limit" in lowered or "rate-limited" in lowered:
        return "rate_limit"
    if "402" in lowered or "payment required" in lowered or "spend limit" in lowered:
        return "billing_limit"
    return "provider_error"


@dataclass
class WorkflowState:
    # Shared state passed across team stages.
    question: str
    allowed_views: list[str]
    rag_docs: list[dict[str, Any]] = field(default_factory=list)
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    context: str = ""
    plan: dict[str, Any] = field(default_factory=lambda: {"intent": "kpi", "widgets": ["table", "metric_card"]})
    sql_payload: dict[str, Any] | None = None
    assistant_artifact: dict[str, Any] | None = None
    validated_sql: str = ""
    views_used: list[str] = field(default_factory=list)
    answer: str = ""


class SchemaRagAgent:
    def __init__(self) -> None:
        self.agent = None

    def run(self, rag_docs: list[dict[str, Any]]) -> str:
        if not rag_docs:
            return "No RAG context documents available."
        return "\n".join(
            [f"- [{d.get('doc_type', 'doc')}] {d.get('source', 'unknown')}: {d.get('content', '')[:300]}" for d in rag_docs]
        )


class SQLAgent:
    def __init__(self) -> None:
        self.last_model_used: str | None = None
        self.instructions = (
            "You are a SQL generation agent for Postgres analytics. "
            "Return JSON only with keys: query, explain, risk. "
            "The query must be one single SELECT or WITH...SELECT statement. "
            "Use only explicitly allowed views and include LIMIT <= 200."
        )

    def _model_candidates(self, primary: str) -> list[str]:
        # Try primary first, then unique fallbacks in order.
        fallback_raw = os.getenv("OPENROUTER_FALLBACK_MODELS", "")
        fallback = [m.strip() for m in fallback_raw.split(",") if m.strip()]
        ordered = [primary] + fallback
        unique: list[str] = []
        for model_name in ordered:
            if model_name not in unique:
                unique.append(model_name)
        return unique

    def _build_prompt(self, question: str, allowed_views: list[str], rag_context: str) -> str:
        semantic_hints: list[str] = []
        q = question.lower()
        allowed_lower = [v.lower() for v in allowed_views]

        if ("top 10 customers" in q or "top customers" in q) and "v_payment_scoped" in allowed_lower:
            semantic_hints.append(
                "SELECT customer_id, SUM(amount) AS total_amount FROM v_payment_scoped "
                "GROUP BY customer_id ORDER BY total_amount DESC LIMIT 10"
            )

        if ("rental count by name" in q or "rentals by name" in q) and (
            "v_rental_scoped" in allowed_lower and "v_customer_masked" in allowed_lower
        ):
            semantic_hints.append(
                "SELECT c.first_name_masked, c.last_name_masked, COUNT(*) AS rental_count "
                "FROM v_rental_scoped r JOIN v_customer_masked c ON c.customer_id = r.customer_id "
                "GROUP BY c.first_name_masked, c.last_name_masked ORDER BY rental_count DESC LIMIT 20"
            )

        return (
            f"Question: {question}\n"
            f"Allowed views: {', '.join(allowed_views) or 'none'}\n"
            f"RAG context:\n{rag_context}\n"
            f"Semantic hints:\n{chr(10).join(semantic_hints) if semantic_hints else 'none'}\n"
            "Hard rules:\n"
            "- one statement only\n"
            "- SELECT or WITH...SELECT only\n"
            "- no INSERT/UPDATE/DELETE/DDL\n"
            "- use only allowed views\n"
            "- LIMIT <= 200\n"
            "Return JSON only: {\"query\":\"...\",\"explain\":\"...\",\"risk\":\"low|med|high\"}."
        )

    def _run_agno_sql(self, prompt: str, model_name: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        # Agno-first SQL generation path: one model attempt + strict JSON parse.
        agent = _build_agno_agent("SQLAgent", self.instructions, model_name)
        result = agent.run(prompt)
        text = _extract_agent_text(result)
        parsed_payload = _parse_sql_payload(text)
        if not parsed_payload:
            raise RuntimeError("provider_error_invalid_payload")

        usage = getattr(result, "usage", None)
        if not isinstance(usage, dict):
            usage = {}

        artifact = {
            "content": text,
            "reasoning_details": getattr(result, "reasoning_details", None),
            "model": model_name,
            "prompt": prompt,
            "usage": usage,
            "provider_response_id": getattr(result, "id", "") or "",
            "model_attempts": [],
        }
        return parsed_payload, artifact

    def run(
        self,
        question: str,
        allowed_views: list[str],
        rag_context: str,
        model: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        prompt = self._build_prompt(question, allowed_views, rag_context)
        if conversation_history:
            history_text = "\n".join(
                [f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in conversation_history[-8:]]
            )
            prompt = f"Conversation history:\n{history_text}\n\n{prompt}"

        errors: list[str] = []
        attempts: list[dict[str, Any]] = []

        for model_name in self._model_candidates(model):
            try:
                parsed_payload, assistant_artifact = self._run_agno_sql(prompt, model_name)
                self.last_model_used = model_name
                attempts.append({"model": model_name, "status": "ok"})
                if assistant_artifact is not None:
                    assistant_artifact["model_attempts"] = attempts
                return parsed_payload, assistant_artifact
            except Exception as exc:
                # Keep retry decisions deterministic for API-level error mapping.
                status = _classify_model_error(str(exc))
                attempts.append({"model": model_name, "status": status})
                errors.append(f"{model_name}: {status}")
                continue

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
            [f"[{d.get('doc_type', 'doc')}] {d.get('source', 'unknown')}: {d.get('content', '')[:280]}" for d in rag_docs]
        )


class RagContextTool:
    # Tool abstraction: central place to build retrieval context.
    def __init__(self, schema_agent: SchemaRagAgent, knowledge_agent: KnowledgeAgent) -> None:
        self.schema_agent = schema_agent
        self.knowledge_agent = knowledge_agent

    def run(self, rag_docs: list[dict[str, Any]]) -> str:
        rag_context = self.schema_agent.run(rag_docs)
        knowledge_context = self.knowledge_agent.run(rag_docs)
        return f"{rag_context}\nKnowledge:\n{knowledge_context}"


class SqlValidationTool:
    # Deterministic safety tool: never delegate this to probabilistic agents.
    def __init__(self, validator_agent: "Validator") -> None:
        self.validator_agent = validator_agent

    def run(self, sql_payload: dict[str, Any], allowed_views: list[str]) -> tuple[str, list[str]]:
        candidate_sql = self.validator_agent.run(str(sql_payload["query"]))
        return validate_sql(candidate_sql, allowed_views)


class WorkflowMemory:
    # Lightweight in-process memory for team coordination metadata.
    def __init__(self, max_turns: int = 20) -> None:
        self.max_turns = max_turns
        self._turns: list[dict[str, str]] = []

    def build_context(self, conversation_history: list[dict[str, Any]]) -> str:
        if not conversation_history:
            return ""
        recent = conversation_history[-8:]
        lines = [f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in recent]
        return "\n".join(lines)

    def remember_sql_attempt(self, question: str, sql_payload: dict[str, Any]) -> None:
        self._turns.append(
            {
                "type": "sql",
                "question": question[:250],
                "query": str(sql_payload.get("query", ""))[:500],
            }
        )
        self._turns = self._turns[-self.max_turns :]

    def remember_answer(self, question: str, answer: str) -> None:
        self._turns.append(
            {
                "type": "answer",
                "question": question[:250],
                "answer": answer[:500],
            }
        )
        self._turns = self._turns[-self.max_turns :]

    def recent_notes(self) -> str:
        if not self._turns:
            return ""
        snippets = []
        for turn in self._turns[-4:]:
            if turn.get("type") == "sql":
                snippets.append(f"Previous SQL for similar question: {turn.get('query', '')}")
            elif turn.get("type") == "answer":
                snippets.append(f"Previous answer style: {turn.get('answer', '')}")
        return "\n".join(snippets)


class PlannerAgent:
    def __init__(self) -> None:
        self.agent = None
        self.instructions = (
            "Classify analytics question intent. Return JSON only: "
            "{\"intent\":\"kpi|trend|ranking|distribution|comparison\"}."
        )

    def run(self, question: str) -> dict[str, Any]:
        # Intent classification via Agno agent, with heuristic fallback for resilience.
        if AGNO_AVAILABLE:
            try:
                model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
                self.agent = _build_agno_agent("PlannerAgent", self.instructions, model)
                result = self.agent.run(f"Question: {question}")
                parsed_intent = _parse_intent_payload(_extract_agent_text(result))
                if parsed_intent:
                    return {"intent": parsed_intent, "widgets": _widgets_for_intent(parsed_intent)}
            except Exception:
                pass

        intent = _heuristic_intent(question)
        return {"intent": intent, "widgets": _widgets_for_intent(intent)}


class AnalyticsAgentTeam:
    # Team facade coordinating specialist agents.
    def __init__(self, planner_agent: PlannerAgent, sql_agent: SQLAgent, narrator_agent: NarratorAgent) -> None:
        self.planner_agent = planner_agent
        self.sql_agent = sql_agent
        self.narrator_agent = narrator_agent

    def plan(self, state: WorkflowState) -> WorkflowState:
        state.plan = self.planner_agent.run(state.question)
        return state

    def draft_sql(self, state: WorkflowState, model: str) -> WorkflowState:
        state.sql_payload, state.assistant_artifact = self.sql_agent.run(
            state.question,
            state.allowed_views,
            state.context,
            model,
            conversation_history=state.conversation_history,
        )
        return state

    def narrate(self, state: WorkflowState, draft_answer: str) -> WorkflowState:
        state.answer = self.narrator_agent.run(draft_answer, state.question)
        return state


class AgnoAnalyticsWorkflow:
    # Thin orchestrator that keeps step ordering explicit and testable.
    def __init__(self) -> None:
        self.schema_rag_agent = SchemaRagAgent()
        self.sql_agent = SQLAgent()
        self.validator_agent = Validator()
        self.insight_agent = InsightAgent()
        self.narrator_agent = NarratorAgent()
        self.knowledge_agent = KnowledgeAgent()
        self.planner_agent = PlannerAgent()
        self.rag_tool = RagContextTool(self.schema_rag_agent, self.knowledge_agent)
        self.sql_validation_tool = SqlValidationTool(self.validator_agent)
        self.memory = WorkflowMemory()
        self.team = AnalyticsAgentTeam(self.planner_agent, self.sql_agent, self.narrator_agent)

    @property
    def last_model_used(self) -> str | None:
        return self.sql_agent.last_model_used

    def build_context_and_plan(self, question: str, rag_docs: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        # Workflow step 1: retrieval tool + team planning.
        state = WorkflowState(question=question, allowed_views=[], rag_docs=rag_docs)
        state.context = self.rag_tool.run(rag_docs)
        state = self.team.plan(state)
        notes = self.memory.recent_notes()
        if notes:
            state.context = f"{state.context}\nTeam memory:\n{notes}"
        return state.context, state.plan

    def generate_sql(
        self,
        question: str,
        allowed_views: list[str],
        context: str,
        model: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        # Workflow step 2: team SQL draft using retrieval context + conversation memory.
        state = WorkflowState(
            question=question,
            allowed_views=allowed_views,
            context=context,
            conversation_history=conversation_history or [],
        )
        memory_context = self.memory.build_context(state.conversation_history)
        if memory_context:
            state.context = f"Conversation memory:\n{memory_context}\n\n{state.context}"
        state = self.team.draft_sql(state, model)
        if state.sql_payload:
            self.memory.remember_sql_attempt(question, state.sql_payload)
        return state.sql_payload or {"query": "SELECT 1"}, state.assistant_artifact

    def validate_sql(self, sql_payload: dict[str, Any], allowed_views: list[str]) -> tuple[str, list[str]]:
        # Safety boundary: final SQL must pass static validator before execution.
        validated_sql, views_used = self.sql_validation_tool.run(sql_payload, allowed_views)
        executable_sql = self._apply_known_view_fixes(validated_sql)
        return executable_sql, views_used

    def build_answer(self, rows: list[tuple[Any, ...]], columns: list[str], question: str) -> str:
        # Workflow step 3: insight draft + team narrator rewrite.
        state = WorkflowState(question=question, allowed_views=[])
        draft = self.insight_agent.run(rows, columns)
        state = self.team.narrate(state, draft)
        self.memory.remember_answer(question, state.answer)
        return state.answer

    def _apply_known_view_fixes(self, sql: str) -> str:
        # Normalize masked customer columns when model references raw names.
        fixed = sql
        lowered = sql.lower()
        if "v_customer_masked" in lowered:
            fixed = re.sub(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.first_name\b", r"\1.first_name_masked", fixed)
            fixed = re.sub(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.last_name\b", r"\1.last_name_masked", fixed)
            fixed = re.sub(r"\bfirst_name\b(?!_masked)", "first_name_masked", fixed)
            fixed = re.sub(r"\blast_name\b(?!_masked)", "last_name_masked", fixed)
        return fixed


class DBTool:
    def run(self, query: str) -> str:
        return query


class WidgetAgent:
    def run(self) -> dict[str, Any]:
        return {"ok": True}
