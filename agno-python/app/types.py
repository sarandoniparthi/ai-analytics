from typing import Any

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    role: str
    store_id: int
    allowed_views: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    conversation_id: str
    question: str
    org_id: str = "default-org"
    user_id: str = "default-user"
    user_context: UserContext


class SqlPayload(BaseModel):
    query: str


class ExplainPayload(BaseModel):
    views_used: list[str] = Field(default_factory=list)
    notes: str = ""


class SecurityPayload(BaseModel):
    role: str
    store_id: int
    rls: bool = True
    allowed_views: list[str] = Field(default_factory=list)


class MetaPayload(BaseModel):
    rows: int
    exec_ms: int
    model: str
    confidence: str


class RunResponse(BaseModel):
    conversation_id: str
    answer: str
    insights: list[str] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    intent: str = "kpi"
    sql: SqlPayload
    widgets: list[Any] = Field(default_factory=list)
    explain: ExplainPayload
    security: SecurityPayload
    lineage: dict[str, Any] = Field(default_factory=dict)
    meta: MetaPayload
