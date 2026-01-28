import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "ledger.sqlite3"
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def utc_now_iso() -> str:
	return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(s: str) -> str:
	return hashlib.sha256(s.encode("utf-8")).hexdigest()


def ensure_schema_migrations(conn: sqlite3.Connection) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS schema_migrations (
			name TEXT PRIMARY KEY,
			sha256 TEXT NOT NULL,
			applied_at TEXT NOT NULL
		)
		"""
	)


def list_migration_files() -> list[Path]:
	if not MIGRATIONS_DIR.exists():
		return []
	files = [p for p in MIGRATIONS_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".sql"]
	return sorted(files, key=lambda p: p.name)


def apply_migration(conn: sqlite3.Connection, path: Path) -> None:
	sql = path.read_text(encoding="utf-8")
	name = path.name
	digest = sha256_text(sql)

	row = conn.execute("SELECT sha256 FROM schema_migrations WHERE name = ?", (name,)).fetchone()
	if row is not None:
		if row[0] != digest:
			raise RuntimeError(
				f"Migration content changed after apply: {name}\n"
				f"Recorded sha256={row[0]}\n"
				f"Current  sha256={digest}\n"
				f"Fix by creating a NEW migration file; never edit applied migrations."
			)
		return

	with conn:
		conn.executescript(sql)
		conn.execute(
			"INSERT INTO schema_migrations (name, sha256, applied_at) VALUES (?, ?, ?)",
			(name, digest, utc_now_iso()),
		)


def main() -> None:
	MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
	DB_PATH.parent.mkdir(parents=True, exist_ok=True)

	conn = sqlite3.connect(str(DB_PATH))
	try:
		conn.execute("PRAGMA foreign_keys = ON")
		ensure_schema_migrations(conn)

		files = list_migration_files()
		for f in files:
			apply_migration(conn, f)
	finally:
		conn.close()

	print(f"OK: migrations applied (if needed) to {DB_PATH}")


if __name__ == "__main__":
	main()
