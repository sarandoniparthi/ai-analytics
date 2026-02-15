CREATE TABLE IF NOT EXISTS query_audit_logs (
  id BIGSERIAL PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  question TEXT NOT NULL,
  role TEXT NOT NULL,
  store_id INTEGER NOT NULL,
  allowed_views JSONB NOT NULL DEFAULT '[]'::jsonb,
  llm_model TEXT,
  llm_prompt TEXT,
  llm_response TEXT,
  generated_sql TEXT,
  final_answer TEXT,
  status TEXT NOT NULL DEFAULT 'received',
  error_stage TEXT,
  error_message TEXT,
  rows_count INTEGER,
  exec_ms INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS query_audit_logs_conversation_id_idx
  ON query_audit_logs (conversation_id);

CREATE INDEX IF NOT EXISTS query_audit_logs_status_idx
  ON query_audit_logs (status);

CREATE INDEX IF NOT EXISTS query_audit_logs_created_at_idx
  ON query_audit_logs (created_at DESC);
