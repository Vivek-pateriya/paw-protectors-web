BEGIN;
ALTER TABLE users ADD COLUMN session_version integer NOT NULL DEFAULT 0;
CREATE TABLE password_resets (
 user_id bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 token_hash text NOT NULL UNIQUE,
 expires_at timestamptz NOT NULL,
 requested_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE recovery_rate_limits (
 key_hash text PRIMARY KEY,
 window_at timestamptz NOT NULL DEFAULT now(),
 attempts integer NOT NULL DEFAULT 1
);
INSERT INTO schema_versions(version) VALUES(3);
COMMIT;
