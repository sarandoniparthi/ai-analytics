import re

from fastapi import HTTPException


FORBIDDEN_KEYWORDS = [
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "grant",
    "revoke",
    "truncate",
    "copy",
]


def extract_views(sql: str) -> list[str]:
    matches = re.findall(r"\b(?:from|join)\s+([a-zA-Z0-9_.\"]+)", sql, flags=re.IGNORECASE)
    views = []
    for m in matches:
        name = m.replace('"', "").strip().lower()
        if name:
            views.append(name)
    return views


def extract_cte_names(sql: str) -> set[str]:
    lowered = sql.lower()
    matches = re.findall(
        r"(?:\bwith\b(?:\s+recursive)?\s+|,\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(",
        lowered,
        flags=re.IGNORECASE,
    )
    return {m.strip().lower() for m in matches if m.strip()}


def validate_sql(query: str, allowed_views: list[str]) -> tuple[str, list[str]]:
    normalized = " ".join(query.strip().split())
    lowered = normalized.lower()

    semicolons = normalized.count(";")
    if semicolons > 1:
        raise HTTPException(status_code=400, detail="Only single SQL statement is allowed.")
    if semicolons == 1 and not normalized.endswith(";"):
        raise HTTPException(status_code=400, detail="Semicolon is allowed only at query end.")
    if normalized.endswith(";"):
        normalized = normalized[:-1].strip()
        lowered = normalized.lower()

    if not (lowered.startswith("select ") or lowered.startswith("with ")):
        raise HTTPException(status_code=400, detail="Only SELECT/CTE queries are allowed.")

    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise HTTPException(status_code=400, detail=f"Forbidden SQL keyword: {keyword}")

    views_used = extract_views(normalized)
    cte_names = extract_cte_names(normalized)
    allowed_lower = [v.lower() for v in allowed_views]
    for view_name in views_used:
        if view_name in cte_names:
            continue
        if not any(allowed in view_name for allowed in allowed_lower):
            raise HTTPException(status_code=400, detail=f"View not allowed: {view_name}")

    if not re.search(r"\blimit\s+\d+\b", lowered):
        normalized = f"{normalized} LIMIT 200"

    return normalized, views_used
