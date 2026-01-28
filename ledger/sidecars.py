import json
from pathlib import Path
from datetime import datetime


def write_sidecar(document_id, *, kind, source_type, source_locator, event, attachment):
	path = Path("state/docs") / f"{document_id}.json"

	now = datetime.utcnow().isoformat() + "Z"

	data = {
		"document_id": document_id,
		"version": 1,
		"kind": kind,
		"roles": [],
		"entity_id": None,
		"source": {
			"source_type": source_type,
			"source_locator": source_locator,
		},
		"artifacts": {},
		"extractions": {"facts": [], "clauses": [], "line_items": []},
		"timestamps": {
			"created_at": now,
			"updated_at": now,
		},
	}

	if attachment:
		data["artifacts"]["original"] = {
			"filename": attachment.get("filename"),
			"sha256": attachment.get("sha256"),
		}
	else:
		if "archive_pdf" in event:
			data["artifacts"]["rendered_pdf"] = {"path": event["archive_pdf"]}
		if "archive_eml" in event:
			data["artifacts"]["original_eml"] = {"path": event["archive_eml"]}

	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, indent=2))
