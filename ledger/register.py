import uuid
from datetime import datetime
from .sidecars import write_sidecar
from .relationships import upsert_relationship
from .events import emit_event


def utcnow():
	return datetime.utcnow().isoformat() + "Z"


def infer_source(event):
	# Gmail-backed ingest
	if "gmail_message_id" in event:
		return "gmail"
	return "unknown"


def infer_source_locator(event, *, attachment=None):
	# 1) Explicit locator wins (attachments)
	if attachment and attachment.get("sha256"):
		return f"gmail-attachment:{attachment['sha256']}"

	# 2) Stable email identity
	if "parent_identity_key" in event:
		return event["parent_identity_key"]

	if "rfc_message_id" in event and "gmail_account" in event:
		return f"{event['gmail_account']}::{event['rfc_message_id']}"

	if "gmail_message_id" in event and "gmail_account" in event:
		return f"{event['gmail_account']}::{event['gmail_message_id']}"

	raise ValueError("Cannot infer stable source_locator")


def register_document(db, event, *, kind, attachment=None):
	source_type = infer_source(event)
	source_locator = infer_source_locator(event, attachment=attachment)

	doc = db.find_document(source_type, source_locator)

	now = utcnow()

	if not doc:
		document_id = str(uuid.uuid4())
		db.insert_document(
			document_id=document_id,
			source_type=source_type,
			source_locator=source_locator,
			kind=kind,
			created_at=now,
			updated_at=now,
		)
		emit_event(
			"ledger.document_registered",
			{
				"document_id": document_id,
				"source_type": source_type,
				"source_locator": source_locator,
				"kind": kind,
			},
		)
	else:
		document_id = doc["document_id"]

	write_sidecar(
		document_id=document_id,
		kind=kind,
		source_type=source_type,
		source_locator=source_locator,
		event=event,
		attachment=attachment,
	)

	return document_id


def process_event(db, event):
	etype = event.get("event_type")

	if etype == "label_removed":
		return

	if etype not in ("ingest_completed", "ingest_failed"):
		return

	parent_id = register_document(db, event, kind="email_body")

	for att in event.get("attachments", []):
		child_id = register_document(
			db,
			event,
			kind="attachment",
			attachment=att,
		)

		upsert_relationship(
			db,
			relationship_type="parent_of",
			src_type="document",
			src_id=parent_id,
			dst_type="document",
			dst_id=child_id,
			created_by="system",
		)
