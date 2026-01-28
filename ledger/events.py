import json
import uuid
from datetime import datetime
from pathlib import Path


def utcnow():
	return datetime.utcnow().isoformat() + "Z"


def emit_event(event_type, payload):
	event = {
		"event_id": str(uuid.uuid4()),
		"event_type": event_type,
		"created_at": utcnow(),
		"payload": payload,
	}

	Path("state/events").mkdir(parents=True, exist_ok=True)
	log_path = Path("state/events/ledger_events.jsonl")

	with log_path.open("a", encoding="utf-8") as f:
		f.write(json.dumps(event, ensure_ascii=False) + "\n")

	return event
