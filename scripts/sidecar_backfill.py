import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "ledger.sqlite3"
DOCS_DIR = REPO_ROOT / "state" / "docs"


def utcnow() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_documents(con: sqlite3.Connection) -> list[dict]:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM documents").fetchall()
        return [dict(r) for r in rows]


def fetch_relationships(con: sqlite3.Connection) -> list[dict]:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM relationships").fetchall()
        return [dict(r) for r in rows]


def load_existing_sidecar(path: Path) -> dict | None:
        if not path.exists():
                return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None


def merge_sidecar(existing: dict | None, *, doc: dict, rels: list[dict]) -> dict:
        """
        Phase 3.2.3 rule:
        - Preserve any non-derived fields already present (e.g., extracted, annotations).
        - Recompute/overwrite ONLY the `cached` section and authoritative identity fields.
        """
        document_id = doc["document_id"]

        outgoing = [r for r in rels if r["src_id"] == document_id and r["src_type"] == "document"]
        incoming = [r for r in rels if r["dst_id"] == document_id and r["dst_type"] == "document"]

        base = existing.copy() if isinstance(existing, dict) else {}

        base["schema_version"] = base.get("schema_version", 1)
        base["document_id"] = document_id
        base["kind"] = doc.get("kind", "unknown")
        base["sources"] = {
                "source_type": doc.get("source_type", "unknown"),
                "source_locator": doc.get("source_locator", ""),
        }

        base["cached"] = {
                "backfilled_at": utcnow(),
                "relationships": {
                        "outgoing": [
                                {
                                        "relationship_type": r["relationship_type"],
                                        "dst_type": r["dst_type"],
                                        "dst_id": r["dst_id"],
                                        "created_at": r.get("created_at"),
                                        "created_by": r.get("created_by"),
                                }
                                for r in outgoing
                        ],
                        "incoming": [
                                {
                                        "relationship_type": r["relationship_type"],
                                        "src_type": r["src_type"],
                                        "src_id": r["src_id"],
                                        "created_at": r.get("created_at"),
                                        "created_by": r.get("created_by"),
                                }
                                for r in incoming
                        ],
                },
        }

        return base


def main() -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--prune", action="store_true", help="Delete sidecars not present in sqlite ledger")
        args = parser.parse_args()

        with sqlite3.connect(str(DB_PATH)) as con:
                docs = fetch_documents(con)
                rels = fetch_relationships(con)

        DOCS_DIR.mkdir(parents=True, exist_ok=True)

        live_ids = {d["document_id"] for d in docs}

        wrote = 0
        for d in docs:
                path = DOCS_DIR / f"{d['document_id']}.json"
                existing = load_existing_sidecar(path)
                merged = merge_sidecar(existing, doc=d, rels=rels)
                path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                wrote += 1

        pruned = 0
        if args.prune:
                for fp in DOCS_DIR.glob("*.json"):
                        doc_id = fp.stem
                        if doc_id not in live_ids:
                                fp.unlink(missing_ok=True)
                                pruned += 1

        print(f"OK: wrote {wrote} sidecars from sqlite into {DOCS_DIR}")
        if args.prune:
                print(f"OK: pruned {pruned} stale sidecars")


if __name__ == "__main__":
        main()
