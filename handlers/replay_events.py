import json
from pathlib import Path

EVENT_LOG_PATH = Path(r"C:\Users\tragh\Nextcloud\DocSystem\state\ingest_events.jsonl")

def main():
	if not EVENT_LOG_PATH.exists():
		print("Missing:", EVENT_LOG_PATH)
		return

	total = 0
	completed = 0
	failed = 0
	labels = 0

	by_msg = {}

	for line in EVENT_LOG_PATH.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if not line:
			continue
		total += 1
		try:
			e = json.loads(line)
		except Exception:
			continue

		key = (str(e.get("gmail_account") or "").strip().lower(), str(e.get("gmail_message_id") or "").strip())
		etype = str(e.get("event_type") or "")

		by_msg.setdefault(key, []).append(etype)

		if etype == "ingest_completed":
			completed += 1
		elif etype == "ingest_failed":
			failed += 1
		elif etype == "label_removed":
			labels += 1

	print("events_total:", total)
	print("messages_seen:", len(by_msg))
	print("ingest_completed:", completed)
	print("ingest_failed:", failed)
	print("label_removed:", labels)

	missing_label = [k for k, v in by_msg.items() if "ingest_completed" in v and "label_removed" not in v]
	if missing_label:
		print("WARNING: completed but label not removed:", len(missing_label))
		for k in missing_label[:10]:
			print(" ", k[1])

if __name__ == "__main__":
	main()