ALTER TABLE query_audit_logs
  ADD COLUMN IF NOT EXISTS org_id TEXT,
  ADD COLUMN IF NOT EXISTS user_id TEXT,
  ADD COLUMN IF NOT EXISTS correlation_id TEXT,
  ADD COLUMN IF NOT EXISTS rag_sources JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS rag_doc_ids JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS widgets JSONB,
  ADD COLUMN IF NOT EXISTS final_response JSONB,
  ADD COLUMN IF NOT EXISTS llm_usage JSONB,
  ADD COLUMN IF NOT EXISTS model_attempts JSONB,
  ADD COLUMN IF NOT EXISTS error_code TEXT,
  ADD COLUMN IF NOT EXISTS llm_input_tokens INTEGER,
  ADD COLUMN IF NOT EXISTS llm_output_tokens INTEGER,
  ADD COLUMN IF NOT EXISTS llm_total_tokens INTEGER,
  ADD COLUMN IF NOT EXISTS llm_cost_usd NUMERIC(12,6),
  ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rag_ms INTEGER,
  ADD COLUMN IF NOT EXISTS llm_ms INTEGER,
  ADD COLUMN IF NOT EXISTS validation_ms INTEGER,
  ADD COLUMN IF NOT EXISTS total_ms INTEGER,
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days');

CREATE TABLE IF NOT EXISTS query_audit_events (
  id BIGSERIAL PRIMARY KEY,
  log_id BIGINT NOT NULL REFERENCES query_audit_logs(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  message TEXT,
  duration_ms INTEGER,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS query_audit_logs_error_code_idx
  ON query_audit_logs (error_code);

CREATE INDEX IF NOT EXISTS query_audit_logs_expires_at_idx
  ON query_audit_logs (expires_at);

CREATE INDEX IF NOT EXISTS query_audit_events_log_id_idx
  ON query_audit_events (log_id);

CREATE INDEX IF NOT EXISTS query_audit_events_stage_idx
  ON query_audit_events (stage);

CREATE OR REPLACE FUNCTION cleanup_query_audit_logs(retention_days INTEGER DEFAULT 90)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
  deleted_count BIGINT;
BEGIN
  DELETE FROM query_audit_logs
  WHERE created_at < NOW() - make_interval(days => retention_days);

  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$;
