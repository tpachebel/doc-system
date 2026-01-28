import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "ledger.sqlite3"
EVENTS_PATH = ROOT / "state" / "events" / "ledger_repairs.jsonl"


def utcnow() -> str:
	return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_existing_event_ids(path: Path) -> set[str]:
	if not path.exists():
		return set()
	existing = set()
	with path.open("r", encoding="utf-8") as handle:
		for line in handle:
			line = line.strip()
			if not line:
				continue
			try:
				payload = json.loads(line)
			except json.JSONDecodeError:
				continue
			rel_id = payload.get("relationship_id") if isinstance(payload, dict) else None
			if rel_id:
				existing.add(rel_id)
	return existing


def fetch_document_ids(con: sqlite3.Connection) -> set[str]:
	rows = con.execute("SELECT document_id FROM documents").fetchall()
	return {row[0] for row in rows}


def fetch_relationships(con: sqlite3.Connection) -> list[sqlite3.Row]:
	return con.execute("SELECT * FROM relationships").fetchall()


def find_invalid_relationships(
	rows: list[sqlite3.Row], document_ids: set[str]
) -> list[tuple[sqlite3.Row, list[str]]]:
	invalid: list[tuple[sqlite3.Row, list[str]]] = []
	for row in rows:
		reasons: list[str] = []
		if (
			row["relationship_type"] == "parent_of"
			and row["src_type"] == row["dst_type"]
			and row["src_id"] == row["dst_id"]
		):
			reasons.append("self_loop_parent_of")
		if row["src_type"] == "document" and row["src_id"] not in document_ids:
			reasons.append("dangling_document_src")
		if row["dst_type"] == "document" and row["dst_id"] not in document_ids:
			reasons.append("dangling_document_dst")
		if reasons:
			invalid.append((row, reasons))
	return invalid


def append_events(path: Path, events: list[dict]) -> None:
	if not events:
		return
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("a", encoding="utf-8") as handle:
		for event in events:
			handle.write(json.dumps(event, sort_keys=True) + "\n")


def delete_relationships(con: sqlite3.Connection, relationship_ids: list[str]) -> int:
	deleted = 0
	for rel_id in relationship_ids:
		cursor = con.execute("DELETE FROM relationships WHERE relationship_id=?", (rel_id,))
		deleted += cursor.rowcount
	return deleted


def main() -> int:
	if not DB_PATH.exists():
		print(f"ERROR: missing database at {DB_PATH}")
		return 1

	with sqlite3.connect(str(DB_PATH)) as con:
		con.row_factory = sqlite3.Row
		document_ids = fetch_document_ids(con)
		rows = fetch_relationships(con)
		invalid = find_invalid_relationships(rows, document_ids)

		existing_event_ids = load_existing_event_ids(EVENTS_PATH)
		events: list[dict] = []
		relationship_ids: list[str] = []
		for row, reasons in invalid:
			rel_id = row["relationship_id"]
			rel_snapshot = dict(row)
			reason = "; ".join(reasons)
			relationship_ids.append(rel_id)
			if rel_id not in existing_event_ids:
				events.append(
					{
						"ts_utc": utcnow(),
						"action": "delete_relationship",
						"relationship_id": rel_id,
						"reason": reason,
						"relationship_row_snapshot": rel_snapshot,
					}
				)

		deleted = delete_relationships(con, relationship_ids)
		append_events(EVENTS_PATH, events)

	print(f"Invalid relationships detected: {len(invalid)}")
	print(f"Relationships deleted: {deleted}")
	if relationship_ids:
		print("Removed relationship_ids:")
		for rel_id in relationship_ids:
			print(f"- {rel_id}")
	else:
		print("Removed relationship_ids: none")
	print(f"Repair events logged: {len(events)}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
