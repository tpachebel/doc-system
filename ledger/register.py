import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional

from .events import emit_event
from .sidecars import write_sidecar, write_transaction_sidecar


def utcnow() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_text(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_source_fingerprint(source_type: str, source_locator: str, *, kind: str) -> str:
        # Stable across replays and independent of document_id.
        # Keep minimal inputs for now; expand later with sha256/bytes when available.
        payload = {
                "v": 1,
                "source_type": source_type,
                "source_locator": source_locator,
                "kind": kind,
        }
        return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


# ---------- Documents ----------

def infer_source(event: dict) -> str:
        if "gmail_message_id" in event or event.get("source_type") == "gmail":
                return "gmail"
        return event.get("source_type", "unknown") or "unknown"


def infer_source_locator(event: dict, *, attachment: Optional[dict] = None) -> str:
        if attachment and attachment.get("sha256"):
                return f"gmail-attachment:{attachment['sha256']}"

        if "parent_identity_key" in event:
                return event["parent_identity_key"]

        if "rfc_message_id" in event and "gmail_account" in event:
                return f"{event['gmail_account']}::{event['rfc_message_id']}"

        if "gmail_message_id" in event and "gmail_account" in event:
                return f"{event['gmail_account']}::{event['gmail_message_id']}"

        if "source_locator" in event:
                return event["source_locator"]

        raise ValueError("Cannot infer stable source_locator")


def register_document(db, event: dict, *, kind: str, attachment: Optional[dict] = None) -> str:
        source_type = infer_source(event)
        source_locator = infer_source_locator(event, attachment=attachment)

        fp = compute_source_fingerprint(source_type, source_locator, kind=kind)
        now = utcnow()

        # Hard dedup by fingerprint (preferred)
        existing_fp = db.find_document_by_fingerprint(fp)
        if existing_fp:
            # Ensure sidecar exists/updated (Phase 3.2.3 semantics)
            write_sidecar(
                    existing_fp["document_id"],
                    kind=existing_fp["kind"],
                    source_type=existing_fp["source_type"],
                    source_locator=existing_fp["source_locator"],
                    event=event,
                    attachment=attachment,
            )
            emit_event(
                    "ledger.document_reused",
                    {"document_id": existing_fp["document_id"], "source_fingerprint": fp},
            )
            return existing_fp["document_id"]

        # Fallback dedup by (source_type, source_locator)
        existing = db.find_document(source_type, source_locator)
        if existing:
                # Backfill fingerprint if missing (important for Phase 3.3 hard dedup going forward)
                if not existing["source_fingerprint"]:
                        db.update_document(existing["document_id"], {"source_fingerprint": fp, "updated_at": now})
                        emit_event(
                                "ledger.document_updated",
                                {
                                        "document_id": existing["document_id"],
                                        "source_type": source_type,
                                        "source_locator": source_locator,
                                        "kind": existing["kind"],
                                        "source_fingerprint": fp,
                                },
                        )

                write_sidecar(
                        existing["document_id"],
                        kind=existing["kind"],
                        source_type=source_type,
                        source_locator=source_locator,
                        event=event,
                        attachment=attachment,
                )
                emit_event(
                        "ledger.document_reused",
                        {"document_id": existing["document_id"], "source_fingerprint": existing["source_fingerprint"] or fp},
                )
                return existing["document_id"]

        # Create new
        document_id = str(uuid.uuid4())
        db.insert_document(
                document_id=document_id,
                source_type=source_type,
                source_locator=source_locator,
                kind=kind,
                created_at=now,
                updated_at=now,
                source_fingerprint=fp,
                roles_json="[]",
                entity_id=None,
                title=None,
                original_filename=None,
                mime_type=None,
                byte_size=None,
                sha256=attachment.get("sha256") if attachment else None,
        )

        write_sidecar(
                document_id,
                kind=kind,
                source_type=source_type,
                source_locator=source_locator,
                event=event,
                attachment=attachment,
        )

        emit_event(
                "ledger.document_registered",
                {
                        "document_id": document_id,
                        "source_type": source_type,
                        "source_locator": source_locator,
                        "kind": kind,
                        "entity_id": None,
                        "roles": [],
                        "source_fingerprint": fp,
                },
        )
        return document_id


# ---------- Transactions ----------

def register_transaction(db, txn: dict):
        existing = db.find_transaction_by_source(
                txn["source_type"],
                txn["source_locator"],
        )

        now = utcnow()

        if not existing:
                txn["created_at"] = now
                txn["updated_at"] = now
                db.insert_transaction(txn)
                emit_event("ledger.transaction_registered", {"txn_id": txn["txn_id"]})
                write_transaction_sidecar(txn)
                return txn["txn_id"]

        updates = {}
        for k in (
                "amount",
                "currency",
                "txn_date",
                "description",
                "counterparty",
                "account_id",
                "entity_id",
                "status",
        ):
                if existing[k] != txn.get(k):
                        updates[k] = txn.get(k)

        if updates:
                updates["updated_at"] = now
                db.update_transaction(existing["txn_id"], updates)
                emit_event("ledger.transaction_updated", {"txn_id": existing["txn_id"]})
                txn["created_at"] = existing["created_at"]
                txn["updated_at"] = now
                write_transaction_sidecar(txn)

        return existing["txn_id"]


# ---------- Document ↔ Transaction linking ----------

def link_document_transaction(
        db,
        *,
        document_id: str,
        txn: dict,
        link_type: str,
        confidence: float = 1.0,
        created_by: str = "system",
        evidence_json: dict | None = None,
):
        row = {
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "txn_id": txn["txn_id"],
                "link_type": link_type,
                "confidence": confidence,
                "created_by": created_by,
                "evidence_json": "{}" if evidence_json is None else json.dumps(evidence_json, sort_keys=True),
                "created_at": utcnow(),
        }

        inserted = db.upsert_document_transaction_link(row)
        if not inserted:
                return False

        emit_event(
                "ledger.document_txn_link_upserted",
                {
                        "document_id": document_id,
                        "txn_id": txn["txn_id"],
                        "link_type": link_type,
                },
        )

        write_transaction_sidecar(
                txn,
                links=[
                        {
                                "document_id": document_id,
                                "link_type": link_type,
                                "confidence": confidence,
                                "created_by": created_by,
                                "evidence_json": evidence_json or {},
                        }
                ],
        )

        return True
