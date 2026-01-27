import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64
import email
import re
import hashlib
import sqlite3
from datetime import datetime
from email.policy import default

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from handlers.paperless_client import PaperlessClient
from handlers.email_render import render_email_pdf
from handlers.gmail_config import SCOPES, TOKEN_PATH, LABEL_NAME, MAX_MESSAGES_PER_RUN


EMAIL_ARCHIVE_ROOT = Path(r"C:\Users\tragh\Nextcloud\DocSystem\Email-Archive")
ATTACH_DB = Path(r"C:\Users\tragh\Nextcloud\DocSystem\state\attachment_dedupe.sqlite3")


def _sha256(data: bytes) -> str:
	h = hashlib.sha256()
	h.update(data)
	return h.hexdigest()


def _safe_msgid(msgid: str) -> str:
	if not msgid:
		return "no-message-id"
	s = msgid.strip().strip("<>").replace("/", "_")
	s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
	return s[:180]


def _ensure_dir(p: Path):
	p.mkdir(parents=True, exist_ok=True)


def _parse_date(msg) -> tuple[str, str]:
	raw = msg.get("Date", "")
	try:
		dt = email.utils.parsedate_to_datetime(raw)
		return dt.date().isoformat(), dt.isoformat()
	except Exception:
		return "", ""


def _get_header(msg, name: str) -> str:
	return str(msg.get(name, "") or "")


def _gmail_service():
	if not TOKEN_PATH.exists():
		print("Gmail token missing — running gmail_auth bootstrap")
		from handlers import gmail_auth
		gmail_auth.main()

	if not TOKEN_PATH.exists():
		raise SystemExit(f"Failed to obtain Gmail token at {TOKEN_PATH}")

	creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
	return build("gmail", "v1", credentials=creds)


def _get_gmail_account_email(service) -> str:
	profile = service.users().getProfile(userId="me").execute()
	addr = profile.get("emailAddress") or ""
	addr = str(addr).strip().lower()
	if not addr:
		raise RuntimeError("Gmail profile did not return emailAddress")
	return addr


def _get_label_id(service, label_name: str) -> str:
	labels = service.users().labels().list(userId="me").execute().get("labels", [])
	for l in labels:
		if l.get("name") == label_name:
			return l.get("id")
	raise SystemExit(f"Gmail label not found: {label_name}")


def _list_message_ids(service, label_id: str, max_results: int):
	resp = service.users().messages().list(userId="me", labelIds=[label_id], maxResults=max_results).execute()
	return [m["id"] for m in resp.get("messages", [])]


def _fetch_raw_eml(service, msg_id: str) -> bytes:
	msg = service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
	raw = msg["raw"]
	return base64.urlsafe_b64decode(raw.encode("utf-8"))


def _iter_attachments(eml_msg):
	for part in eml_msg.walk():
		if part.get_content_maintype() == "multipart":
			continue
		content_disposition = str(part.get("Content-Disposition") or "")
		if "attachment" not in content_disposition.lower():
			continue

		filename = part.get_filename()
		if not filename:
			ext = (part.get_content_subtype() or "bin").lower()
			filename = f"attachment.{ext}"

		data = part.get_payload(decode=True)
		if not data:
			continue

		yield filename, data


def _remove_label(service, msg_id: str, label_id: str):
	service.users().messages().modify(
		userId="me",
		id=msg_id,
		body={"removeLabelIds": [label_id]},
	).execute()


def _find_existing_attachment_legacy(pl: PaperlessClient, locked_key: str, fname: str, email_date: str) -> int | None:
	# Legacy fallback for already-ingested attachments that do not yet have SHA field populated.
	# We match:
	# - Email Message-ID == locked_key
	# - Email Is Parent == False
	# - (optional) Email Date == email_date (if available)
	# Then pick best candidate by title/original filename heuristics.
	locked_key = (locked_key or "").strip()
	fname_norm = (fname or "").strip().lower()
	if not locked_key or not fname_norm:
		return None

	data = pl.get_documents(params={"page_size": 200, "ordering": "-added"})
	items = data.get("results", []) if isinstance(data, dict) else (data or [])

	name_to_id = pl._custom_field_name_to_id_map()
	fid_msgid = name_to_id.get("email message-id")
	fid_is_parent = name_to_id.get("email is parent")
	fid_date = name_to_id.get("email date")

	if not fid_msgid or not fid_is_parent:
		return None

	candidates = []
	for d in items:
		cfs = d.get("custom_fields") or []
		msgid_ok = False
		is_parent_false = False
		date_ok = True

		for cf in cfs:
			fid = int(cf.get("field", -1))
			val = cf.get("value")

			if fid == int(fid_msgid) and str(val or "").strip() == locked_key:
				msgid_ok = True

			if fid == int(fid_is_parent):
				if val is False or str(val).strip().lower() in ("false", "0", "no"):
					is_parent_false = True

			if email_date and fid_date and fid == int(fid_date):
				date_ok = (str(val or "").strip() == email_date)

		if not (msgid_ok and is_parent_false and date_ok):
			continue

		title = str(d.get("title") or "").strip().lower()
		orig = str(d.get("original_file_name") or "").strip().lower()

		score = 0
		if title == fname_norm:
			score += 3
		if orig == fname_norm:
			score += 3
		if fname_norm in title:
			score += 1
		if fname_norm in orig:
			score += 1

		candidates.append((score, int(d["id"])))

	if not candidates:
		return None

	candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
	best_score, best_id = candidates[0]
	if best_score <= 0:
		return None
	return best_id


def main():
	service = _gmail_service()
	gmail_account_email = _get_gmail_account_email(service)

	label_id = _get_label_id(service, LABEL_NAME)
	msg_ids = _list_message_ids(service, label_id, MAX_MESSAGES_PER_RUN)

	if not msg_ids:
		print("No messages to ingest.")
		return

	pl = PaperlessClient()

	db = sqlite3.connect(ATTACH_DB)
	db.execute("PRAGMA journal_mode=WAL")
	cur = db.cursor()

	for mid in msg_ids:
		raw_eml = _fetch_raw_eml(service, mid)
		eml = email.message_from_bytes(raw_eml, policy=default)

		message_id = _get_header(eml, "Message-ID")
		subject = _get_header(eml, "Subject")
		from_ = _get_header(eml, "From")
		to_ = _get_header(eml, "To")
		email_date, email_datetime = _parse_date(eml)

		safe_id = _safe_msgid(message_id)
		year = email_datetime[0:4] if email_datetime else datetime.now().strftime("%Y")
		month = email_datetime[5:7] if email_datetime else datetime.now().strftime("%m")

		archive_dir = EMAIL_ARCHIVE_ROOT / year / month
		_ensure_dir(archive_dir)

		eml_path = archive_dir / f"{safe_id}.eml"
		if not eml_path.exists():
			eml_path.write_bytes(raw_eml)

		pdf_path = archive_dir / f"{safe_id}.pdf"
		render_result = render_email_pdf(eml_path, pdf_path)

		parent_title = render_result.subject or subject or pdf_path.name

		lock = pl.find_or_lock_email_parent(gmail_account_email=gmail_account_email, rfc_message_id=(render_result.message_id or message_id or ""))
		locked_key = lock.get("identity_key") or ""
		existing_parent = lock.get("document")

		parent_fields = {
			"Email Message-ID": locked_key,
			"Email Archive Path": (str(eml_path)[-128:]),
			"Email Subject": render_result.subject or subject or "",
			"Email From": render_result.from_ or from_ or "",
			"Email To": render_result.to or to_ or "",
			"Email Date": email_date or "",
			"Email Is Parent": True,
		}

		if existing_parent:
			parent_id = int(existing_parent["id"])
		else:
			parent_task_id = pl.upload_document(file_path=pdf_path, title=parent_title)
			parent_id = pl.wait_for_task_document_id(parent_task_id, timeout_seconds=240)
			pl.set_tags_by_name(parent_id, ["email", "email-parent"])

		pl.set_custom_fields_by_name(parent_id, parent_fields)

		attach_dir = archive_dir / f"{safe_id}_attachments"
		_ensure_dir(attach_dir)

		for (fname, blob) in _iter_attachments(eml):
			h = _sha256(blob)

			row = cur.execute("SELECT document_id FROM attachment_hash WHERE sha256=?", (h,)).fetchone()
			if row:
				doc_id = int(row[0])
				print(f"Attachment reused (sqlite): {fname} -> doc {doc_id}")
				continue

			existing = pl.find_document_by_custom_field_exact("Email Attachment SHA256", h)
			if existing:
				doc_id = int(existing["id"])
				cur.execute(
					"INSERT OR IGNORE INTO attachment_hash (sha256, document_id) VALUES (?,?)",
					(h, doc_id),
				)
				print(f"Attachment reused (paperless-hash): {fname} -> doc {doc_id}")
				continue

			legacy_doc_id = _find_existing_attachment_legacy(pl, locked_key, fname, email_date)
			if legacy_doc_id:
				# Backfill SHA into Paperless + sqlite for future deterministic dedupe
				pl.set_custom_fields_by_name(legacy_doc_id, {"Email Attachment SHA256": h})
				cur.execute(
					"INSERT OR IGNORE INTO attachment_hash (sha256, document_id) VALUES (?,?)",
					(h, legacy_doc_id),
				)
				print(f"Attachment reused (legacy-match): {fname} -> doc {legacy_doc_id}")
				continue

			out_path = attach_dir / fname
			if out_path.exists():
				stem = out_path.stem
				suffix = out_path.suffix
				i = 2
				while True:
					cand = attach_dir / f"{stem}__{i}{suffix}"
					if not cand.exists():
						out_path = cand
						break
					i += 1
			out_path.write_bytes(blob)

			child_task_id = pl.upload_document(file_path=out_path, title=fname)
			child_id, was_dup = pl.wait_for_task_document_id_and_status(child_task_id, timeout_seconds=240)

			pl.set_tags_by_name(child_id, ["email", "email-attachment"])
			pl.set_custom_fields_by_name(child_id, {
				"Email Parent Doc ID": parent_id,
				"Email Message-ID": locked_key,
				"Email Attachment SHA256": h,
				"Email Date": parent_fields.get("Email Date", ""),
				"Email From": parent_fields.get("Email From", ""),
				"Email To": parent_fields.get("Email To", ""),
				"Email Subject": parent_fields.get("Email Subject", ""),
				"Email Archive Path": parent_fields.get("Email Archive Path", ""),
				"Email Is Parent": False,
			})

			cur.execute(
				"INSERT OR IGNORE INTO attachment_hash (sha256, document_id) VALUES (?,?)",
				(h, int(child_id)),
			)

			if was_dup:
				print(f"Attachment reused (paperless-dup): {fname} -> doc {child_id}")
			else:
				print(f"Attachment uploaded: {fname} -> doc {child_id}")

		db.commit()
		_remove_label(service, mid, label_id)

	db.commit()
	db.close()


if __name__ == "__main__":
	main()