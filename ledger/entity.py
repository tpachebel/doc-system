from __future__ import annotations

from typing import Optional, Dict, Any

from .events import emit_event


def bind_entity_to_document(
        db,
        *,
        document_id: str,
        entity_id: str,
        method: str = "manual",
        confidence: float = 1.0,
        evidence: Optional[Dict[str, Any]] = None,
) -> bool:
        changed = db.set_document_entity(document_id, entity_id)
        if not changed:
                return False

        emit_event(
                "entity.bound",
                {
                        "document_id": document_id,
                        "entity_id": entity_id,
                        "method": method,
                        "confidence": confidence,
                        "evidence": evidence or {},
                },
        )
        return True


def unbind_entity_from_document(
        db,
        *,
        document_id: str,
        method: str = "manual",
        evidence: Optional[Dict[str, Any]] = None,
) -> bool:
        # read prior for event payload
        doc = db.find_document_by_id(document_id)
        if not doc:
                raise ValueError(f"Unknown document_id: {document_id}")

        prior = doc["entity_id"]
        changed = db.set_document_entity(document_id, None)
        if not changed:
                return False

        emit_event(
                "entity.unbound",
                {
                        "document_id": document_id,
                        "prior_entity_id": prior,
                        "method": method,
                        "evidence": evidence or {},
                },
        )
        return True
