import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlite3
from pathlib import Path

from handlers.paperless_client import PaperlessClient

DB_PATH = Path(r"C:\Users\tragh\Nextcloud\DocSystem\state\attachment_dedupe.sqlite3")
FIELD_NAME = "Email Attachment SHA256"

def _has_sha_field(doc: dict) -> bool:
	for cf in (doc.get("custom_fields") or []):
		if str(cf.get("name") or "").strip().lower() == FIELD_NAME.lower():
			v = str(cf.get("value") or "").strip()
			if v:
				return True
	return False

def main():
	pl = PaperlessClient()

	if not DB_PATH.exists():
		raise SystemExit(f"Missing DB: {DB_PATH}")

	conn = sqlite3.connect(DB_PATH)
	cur = conn.cursor()

	rows = cur.execute("SELECT sha256, document_id FROM attachment_hash ORDER BY first_seen ASC").fetchall()
	print(f"rows={len(rows)}")

	ok = 0
	stamped = 0
	purged = 0
	missing = 0
	errors = 0

	for sha256, doc_id in rows:
		sha256 = str(sha256)
		doc_id = int(doc_id)

		try:
			doc = pl.get_document(doc_id)
		except Exception:
			# doc deleted or invalid mapping
			cur.execute("DELETE FROM attachment_hash WHERE sha256=?", (sha256,))
			purged += 1
			missing += 1
			print(f"PURGE missing doc: sha={sha256} doc_id={doc_id}")
			continue

		# Safety: if this is clearly an email parent, purge mapping (bad)
		# We use Email Is Parent custom field by name if present.
		is_parent = None
		for cf in (doc.get("custom_fields") or []):
			if str(cf.get("name") or "").strip().lower() == "email is parent":
				is_parent = cf.get("value")
				break
		if is_parent is True or str(is_parent).strip().lower() in ("true", "1", "yes"):
			cur.execute("DELETE FROM attachment_hash WHERE sha256=?", (sha256,))
			purged += 1
			print(f"PURGE mapped-to-parent: sha={sha256} doc_id={doc_id}")
			continue

		ok += 1

		if _has_sha_field(doc):
			continue

		try:
			pl.set_custom_fields_by_name(doc_id, {FIELD_NAME: sha256})
			stamped += 1
			print(f"STAMPED: doc_id={doc_id} sha={sha256}")
		except Exception as e:
			errors += 1
			print(f"ERROR stamping doc_id={doc_id} sha={sha256}: {e!r}")

	conn.commit()
	conn.close()

	print(f"ok={ok} stamped={stamped} purged={purged} missing={missing} errors={errors}")

if __name__ == "__main__":
	main()