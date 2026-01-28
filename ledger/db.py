import sqlite3


class LedgerDB:
	def __init__(self, path):
		self.con = sqlite3.connect(path)
		self.con.row_factory = sqlite3.Row
		self._init()

	def _init(self):
		c = self.con.cursor()
		c.execute(
			"""
			CREATE TABLE IF NOT EXISTS documents (
				document_id TEXT PRIMARY KEY,
				source_type TEXT NOT NULL,
				source_locator TEXT NOT NULL,
				kind TEXT NOT NULL,
				created_at TEXT NOT NULL,
				updated_at TEXT NOT NULL,
				UNIQUE(source_type, source_locator)
			)
			"""
		)
		c.execute(
			"""
			CREATE TABLE IF NOT EXISTS relationships (
				relationship_id TEXT PRIMARY KEY,
				relationship_type TEXT NOT NULL,
				src_type TEXT NOT NULL,
				src_id TEXT NOT NULL,
				dst_type TEXT NOT NULL,
				dst_id TEXT NOT NULL,
				created_by TEXT NOT NULL,
				created_at TEXT NOT NULL,
				updated_at TEXT NOT NULL,
				UNIQUE(relationship_type, src_type, src_id, dst_type, dst_id)
			)
			"""
		)
		self.con.commit()

	def find_document(self, source_type, source_locator):
		cur = self.con.execute(
			"SELECT * FROM documents WHERE source_type=? AND source_locator=?",
			(source_type, source_locator),
		)
		return cur.fetchone()

	def insert_document(self, *, document_id, source_type, source_locator, kind, created_at, updated_at):
		self.con.execute(
			"""
			INSERT INTO documents
			(document_id, source_type, source_locator, kind, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?, ?)
			""",
			(document_id, source_type, source_locator, kind, created_at, updated_at),
		)
		self.con.commit()

	def document_count(self):
		return self.con.execute("SELECT count(*) FROM documents").fetchone()[0]
