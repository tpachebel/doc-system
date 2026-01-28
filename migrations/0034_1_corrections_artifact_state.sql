BEGIN;

CREATE TABLE IF NOT EXISTS corrections (
	correction_id TEXT PRIMARY KEY,
	scope TEXT NOT NULL,
	target_id TEXT NOT NULL,
	field TEXT NOT NULL,
	old_value TEXT,
	new_value TEXT,
	reason TEXT,
	confidence REAL,
	evidence_json TEXT,
	created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_corrections_scope_target_id
ON corrections (scope, target_id);

CREATE INDEX IF NOT EXISTS idx_corrections_target_id
ON corrections (target_id);

CREATE TABLE IF NOT EXISTS artifact_state (
	artifact_id TEXT PRIMARY KEY,
	artifact_type TEXT NOT NULL,
	target_type TEXT NOT NULL,
	target_id TEXT NOT NULL,
	artifact_ref TEXT,
	sha256 TEXT,
	size_bytes INTEGER,
	status TEXT NOT NULL,
	meta_json TEXT,
	updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifact_state_target_type_target_id
ON artifact_state (target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_artifact_state_artifact_type_target_id
ON artifact_state (artifact_type, target_id);

CREATE INDEX IF NOT EXISTS idx_artifact_state_status
ON artifact_state (status);

COMMIT;
