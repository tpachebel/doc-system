BEGIN;

ALTER TABLE documents ADD COLUMN source_fingerprint TEXT;
ALTER TABLE documents ADD COLUMN roles_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE documents ADD COLUMN entity_id TEXT;

ALTER TABLE documents ADD COLUMN title TEXT;
ALTER TABLE documents ADD COLUMN original_filename TEXT;
ALTER TABLE documents ADD COLUMN mime_type TEXT;
ALTER TABLE documents ADD COLUMN byte_size INTEGER;
ALTER TABLE documents ADD COLUMN sha256 TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_source_fingerprint
ON documents (source_fingerprint);

CREATE INDEX IF NOT EXISTS idx_documents_entity_id ON documents (entity_id);
CREATE INDEX IF NOT EXISTS idx_documents_kind ON documents (kind);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents (sha256);

COMMIT;