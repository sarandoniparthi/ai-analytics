CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_users (
  id BIGSERIAL PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'store_manager', 'marketing', 'finance')),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_all_stores BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app_user_store_access (
  user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  store_id INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, store_id)
);

INSERT INTO app_users (username, password_hash, role, is_active, is_all_stores)
VALUES
  ('admin_user', crypt('admin123', gen_salt('bf')), 'admin', TRUE, TRUE),
  ('manager_store1', crypt('manager123', gen_salt('bf')), 'store_manager', TRUE, FALSE),
  ('manager_multi', crypt('manager123', gen_salt('bf')), 'store_manager', TRUE, FALSE),
  ('marketing_user', crypt('marketing123', gen_salt('bf')), 'marketing', TRUE, FALSE),
  ('finance_user', crypt('finance123', gen_salt('bf')), 'finance', TRUE, FALSE)
ON CONFLICT (username) DO NOTHING;

INSERT INTO app_user_store_access (user_id, store_id)
SELECT id, 1 FROM app_users WHERE username = 'manager_store1'
ON CONFLICT DO NOTHING;

INSERT INTO app_user_store_access (user_id, store_id)
SELECT id, 1 FROM app_users WHERE username = 'manager_multi'
ON CONFLICT DO NOTHING;

INSERT INTO app_user_store_access (user_id, store_id)
SELECT id, 2 FROM app_users WHERE username = 'manager_multi'
ON CONFLICT DO NOTHING;

INSERT INTO app_user_store_access (user_id, store_id)
SELECT id, 1 FROM app_users WHERE username = 'marketing_user'
ON CONFLICT DO NOTHING;

INSERT INTO app_user_store_access (user_id, store_id)
SELECT id, 2 FROM app_users WHERE username = 'marketing_user'
ON CONFLICT DO NOTHING;

INSERT INTO app_user_store_access (user_id, store_id)
SELECT id, 1 FROM app_users WHERE username = 'finance_user'
ON CONFLICT DO NOTHING;
