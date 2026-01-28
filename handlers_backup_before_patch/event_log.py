import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

class EventLog:
	def __init__(self, path: Path):
		self.path = Path(path)
		self.path.parent.mkdir(parents=True, exist_ok=True)
		if not self.path.exists():
			self.path.write_text("", encoding="utf-8")

		self._ingest_done: Set[Tuple[str, str]] = set()
		self._label_done: Set[Tuple[str, str]] = set()
		self._load_index()

	def _load_index(self) -> None:
		self._ingest_done.clear()
		self._label_done.clear()

		with self.path.open("r", encoding="utf-8") as f:
			for line in f:
				line = line.strip()
				if not line:
					continue
				try:
					e = json.loads(line)
				except Exception:
					continue

				gmail_account = str(e.get("gmail_account") or "").strip().lower()
				gmail_id = str(e.get("gmail_message_id") or "").strip()
				etype = str(e.get("event_type") or "").strip()

				if not gmail_account or not gmail_id:
					continue

				if etype == "ingest_completed":
					self._ingest_done.add((gmail_account, gmail_id))
				elif etype == "label_removed":
					self._label_done.add((gmail_account, gmail_id))

	def has_ingest_completed(self, gmail_account: str, gmail_message_id: str) -> bool:
		return (str(gmail_account or "").strip().lower(), str(gmail_message_id or "").strip()) in self._ingest_done

	def has_label_removed(self, gmail_account: str, gmail_message_id: str) -> bool:
		return (str(gmail_account or "").strip().lower(), str(gmail_message_id or "").strip()) in self._label_done

	def append(self, event: Dict[str, Any]) -> None:
		line = json.dumps(event, ensure_ascii=False)
		with self.path.open("a", encoding="utf-8", newline="\n") as f:
			f.write(line + "\n")
			f.flush()
			try:
				os.fsync(f.fileno())
			except Exception:
				pass

		gmail_account = str(event.get("gmail_account") or "").strip().lower()
		gmail_id = str(event.get("gmail_message_id") or "").strip()
		etype = str(event.get("event_type") or "").strip()
		if gmail_account and gmail_id:
			if etype == "ingest_completed":
				self._ingest_done.add((gmail_account, gmail_id))
			elif etype == "label_removed":
				self._label_done.add((gmail_account, gmail_id))