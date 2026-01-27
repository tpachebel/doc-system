import requests
from pathlib import Path

BASE_URL = "https://docs.ragheb.ca"
TOKEN_PATH = Path(r"C:\Users\tragh\Nextcloud\DocSystem\state\secrets\paperless_token.txt")

class PaperlessClient:
	def __init__(self):
		self.base_url = BASE_URL.rstrip("/")
		self.token = TOKEN_PATH.read_text().strip()
		self.headers = {"Authorization": f"Token {self.token}"}

	def get_documents(self, params=None):
		url = f"{self.base_url}/api/documents/"
		resp = requests.get(url, headers=self.headers, params=params)
		resp.raise_for_status()
		return resp.json()

	def get_document(self, doc_id):
		url = f"{self.base_url}/api/documents/{doc_id}/"
		resp = requests.get(url, headers=self.headers)
		resp.raise_for_status()
		return resp.json()

	def upload_document(self, file_path: Path, title: str | None = None):
		url = f"{self.base_url}/api/documents/post_document/"
		data = {}
		if title:
			data["title"] = title

		with open(file_path, "rb") as f:
			files = {"document": (Path(file_path).name, f, "application/pdf")}
			resp = requests.post(url, headers=self.headers, data=data, files=files)
			resp.raise_for_status()
			# Paperless returns a task UUID string (JSON string)
			return resp.json()

	def get_task(self, task_id: str):
		url = f"{self.base_url}/api/tasks/"
		resp = requests.get(url, headers=self.headers, params={"task_id": task_id})
		resp.raise_for_status()
		items = resp.json()
		if isinstance(items, list) and items:
			return items[0]
		return None

	def wait_for_task_document_id(self, task_id: str, timeout_seconds: int = 120) -> int:
		import time
		deadline = time.time() + timeout_seconds
		last = None
		while time.time() < deadline:
			t = self.get_task(task_id)
			last = t
			if isinstance(t, dict):
				# common Paperless field: related_document
				rd = t.get("related_document")
				if isinstance(rd, int) and rd > 0:
					return int(rd)
				if isinstance(rd, str) and rd.strip().isdigit():
					return int(rd.strip())
				
				r = t.get("result")
				if isinstance(r, str):
					import re
					m = re.search(r"\bdocument id\s+(\d+)\b", r, flags=re.IGNORECASE)
					if m:
						return int(m.group(1))

				# fallback: some versions may nest results differently
				res = t.get("result")
				if isinstance(res, dict):
					if "document_id" in res:
						return int(res["document_id"])
					if "related_document" in res:
						return int(res["related_document"])

				# if it explicitly failed, stop early
				status = str(t.get("status") or "").upper()
				if status in ("FAILURE", "FAILED", "ERROR"):
					# Paperless duplicate handling: treat as success if it tells us the existing doc id.
					rd = t.get("related_document")
					if isinstance(rd, int) and rd > 0:
						return int(rd)
					if isinstance(rd, str) and rd.strip().isdigit():
						return int(rd.strip())

					r = t.get("result")
					if isinstance(r, str):
						import re
						m = re.search(r"\(#(\d+)\)", r)
						if m:
							return int(m.group(1))

					raise RuntimeError(f"Task failed: {t}")

			time.sleep(1)

		raise RuntimeError(f"Timeout waiting for task to produce document id. Last task payload: {last}")

	def list_custom_fields(self):
		url = f"{self.base_url}/api/custom_fields/"
		resp = requests.get(url, headers=self.headers)
		resp.raise_for_status()
		return resp.json()

	def _custom_field_name_to_id_map(self) -> dict[str, int]:
		data = self.list_custom_fields()
		m = {}
		results = []
		if isinstance(data, dict) and "results" in data:
			results = data["results"]
		elif isinstance(data, list):
			results = data
		for cf in results:
			name = str(cf.get("name", "")).strip()
			if name:
				m[name.lower()] = int(cf["id"])
		return m

	def set_custom_fields_by_name(self, doc_id: int, values_by_name: dict):
		name_to_id = self._custom_field_name_to_id_map()
		items = []
		for k, v in values_by_name.items():
			if v is None:
				continue
			if isinstance(v, str) and not v.strip():
				continue
			key = str(k).strip().lower()
			if key not in name_to_id:
				raise RuntimeError(f"Paperless custom field not found: {k}")
			field_id = name_to_id[key]
			items.append({"field": field_id, "value": v})

		url = f"{self.base_url}/api/documents/{doc_id}/"
		payload = {"custom_fields": items}
		resp = requests.patch(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
		resp.raise_for_status()
		return resp.json()

	def list_tags(self, name: str | None = None):
		url = f"{self.base_url}/api/tags/"
		params = {}
		if name:
			params["name__iexact"] = name
		resp = requests.get(url, headers=self.headers, params=params)
		resp.raise_for_status()
		return resp.json()

	def create_tag(self, name: str):
		url = f"{self.base_url}/api/tags/"
		resp = requests.post(url, headers={**self.headers, "Content-Type": "application/json"}, json={"name": name})
		resp.raise_for_status()
		return resp.json()

	def ensure_tag_id(self, name: str) -> int:
		name = (name or "").strip()
		if not name:
			raise ValueError("Tag name is empty")

		# Try filtered lookup first (Paperless often returns paginated dict or list depending on version)
		data = self.list_tags(name=name)
		if isinstance(data, dict) and "results" in data:
			for t in data["results"]:
				if str(t.get("name", "")).lower() == name.lower():
					return int(t["id"])
		if isinstance(data, list):
			for t in data:
				if str(t.get("name", "")).lower() == name.lower():
					return int(t["id"])

		# Fallback: create
		created = self.create_tag(name)
		return int(created["id"])

	def set_tags_by_name(self, doc_id: int, tag_names: list[str]):
		tag_ids = [self.ensure_tag_id(n) for n in tag_names]
		url = f"{self.base_url}/api/documents/{doc_id}/"
		resp = requests.patch(url, headers={**self.headers, "Content-Type": "application/json"}, json={"tags": tag_ids})
		resp.raise_for_status()
		return resp.json()

	def set_parent(self, child_doc_id: int, parent_doc_id: int):
		url = f"{self.base_url}/api/documents/{child_doc_id}/"
		payload = {"parent": parent_doc_id}
		resp = requests.patch(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
		resp.raise_for_status()
		return resp.json()
	
	def find_document_by_custom_field(self, field_name: str, exact_value: str):
		# Best-effort search: fetch recent docs and match on custom_fields content.
		# (Paperless search API is version-dependent; this is deterministic.)
		exact_value = (exact_value or "").strip()
		if not exact_value:
			return None

		# Pull recent docs (increase if needed later)
		data = self.get_documents(params={"page_size": 50, "ordering": "-added"})
		items = []
		if isinstance(data, dict) and "results" in data:
			items = data["results"]
		elif isinstance(data, list):
			items = data

		target = exact_value
		for d in items:
			cfs = d.get("custom_fields") or []
			for cf in cfs:
				if str(cf.get("field")) == str(cf.get("field")):
					# we match by name later; easiest is to fetch field map once
					pass
		# Use proper field id mapping:
		name_to_id = self._custom_field_name_to_id_map()
		fid = name_to_id.get((field_name or "").strip().lower())
		if not fid:
			return None

		for d in items:
			for cf in (d.get("custom_fields") or []):
				if int(cf.get("field", -1)) == int(fid) and str(cf.get("value", "")).strip() == target:
					return d
		return None

	def find_email_parent_by_message_id(self, message_id: str):
		message_id = (message_id or "").strip()
		if not message_id:
			return None

		# Must be tagged as email-parent
		email_parent_tag_id = self.ensure_tag_id("email-parent")

		# Pull recent docs and find the one that matches:
		# - tag email-parent
		# - Email Message-ID == message_id
		# - Email Is Parent == True
		data = self.get_documents(params={"page_size": 200, "ordering": "-added"})
		items = data.get("results", []) if isinstance(data, dict) else (data or [])

		name_to_id = self._custom_field_name_to_id_map()
		fid_msgid = name_to_id.get("email message-id")
		fid_is_parent = name_to_id.get("email is parent")
		if not fid_msgid or not fid_is_parent:
			return None

		for d in items:
			tags = d.get("tags") or []
			if email_parent_tag_id not in tags:
				continue

			has_msgid = False
			has_is_parent = False

			for cf in (d.get("custom_fields") or []):
				if int(cf.get("field", -1)) == int(fid_msgid) and str(cf.get("value", "")).strip() == message_id:
					has_msgid = True

				if int(cf.get("field", -1)) == int(fid_is_parent):
					v = cf.get("value")
					if v is True or str(v).strip().lower() in ("true", "1", "yes"):
						has_is_parent = True

			if has_msgid and has_is_parent:
				return d

		return None

	def wait_for_task_document_id_and_status(self, task_id: str, timeout_seconds: int = 120):
		import time

		end = time.time() + timeout_seconds
		last = None

		while time.time() < end:
			t = self.get_task(task_id)
			last = t

			if not t:
				time.sleep(1)
				continue

			status = (t.get("status") or "").upper()
			if status == "SUCCESS":
				return int(t.get("related_document")), False

			if status == "FAILURE":
				# If it’s a duplicate, Paperless returns related_document of the existing doc
				rd = t.get("related_document")
				result = (t.get("result") or "")
				if rd and "duplicate" in str(result).lower():
					return int(rd), True
				raise RuntimeError(f"Task failed: {t}")

			time.sleep(1)

		raise RuntimeError(f"Timeout waiting for task. Last task payload: {last}")
