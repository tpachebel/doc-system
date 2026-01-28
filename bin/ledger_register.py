import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse
import sqlite3
import json
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


def merge_sidecar(existing: dict | None, *, doc: dict, rels: list[dict], docs_by_id: dict[str, dict]) -> dict:
        document_id = doc["document_id"]

        outgoing = [r for r in rels if r["src_id"] == document_id and r["src_type"] == "document"]
        incoming = [r for r in rels if r["dst_id"] == document_id and r["dst_type"] == "document"]

        base = existing.copy() if isinstance(existing, dict) else {}

        base["schema_version"] = base.get("schema_version", 1)
        base["document_id"] = document_id
        base["kind"] = doc.get("kind", "unknown")
        base["entity_id"] = doc.get("entity_id")
        base["sources"] = {
                "source_type": doc.get("source_type", "unknown"),
                "source_locator": doc.get("source_locator", ""),
        }

        candidates = []
        if base["kind"] == "attachment":
                for r in incoming:
                        if r["relationship_type"] != "parent_of":
                                continue
                        if r["src_type"] != "document":
                                continue
                        parent = docs_by_id.get(r["src_id"])
                        if not parent:
                                continue
                        if parent.get("kind") != "email_body":
                                continue
                        if parent.get("entity_id"):
                                candidates.append(
                                        {
                                                "entity_id": parent["entity_id"],
                                                "reason": "parent",
                                                "confidence": 0.7,
                                                "parent_document_id": parent["document_id"],
                                        }
                                )

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
                "entity_candidates": sorted(candidates, key=lambda x: (x["entity_id"], x["parent_document_id"])),
        }

        return base


def main():
        parser = argparse.ArgumentParser()
        parser.add_argument("--prune", action="store_true", help="Delete sidecars not present in sqlite ledger")
        args = parser.parse_args()

        with sqlite3.connect(str(DB_PATH)) as con:
                docs = fetch_documents(con)
                rels = fetch_relationships(con)

        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        live_ids = {d["document_id"] for d in docs}
        docs_by_id = {d["document_id"]: d for d in docs}

        wrote = 0
        for d in docs:
                path = DOCS_DIR / f"{d['document_id']}.json"
                existing = load_existing_sidecar(path)
                merged = merge_sidecar(existing, doc=d, rels=rels, docs_by_id=docs_by_id)
                path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                wrote += 1

        pruned = 0
        if args.prune:
                for fp in DOCS_DIR.glob("*.json"):
                        if fp.stem not in live_ids:
                                fp.unlink(missing_ok=True)
                                pruned += 1

        print(f"OK: replay/backfill wrote {wrote} sidecars from sqlite into {DOCS_DIR}")
        if args.prune:
                print(f"OK: replay/backfill pruned {pruned} stale sidecars")


if __name__ == "__main__":
        main()
