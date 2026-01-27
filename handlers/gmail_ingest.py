import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64
import email
import re
from datetime import datetime
from email.policy import default
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from handlers.paperless_client import PaperlessClient
from handlers.email_render import render_email_pdf

from handlers.gmail_config import SCOPES, TOKEN_PATH, LABEL_NAME, MAX_MESSAGES_PER_RUN


EMAIL_ARCHIVE_ROOT = Path(r"C:\Users\tragh\Nextcloud\DocSystem\Email-Archive")


def _safe_msgid(msgid: str) -> str:
	if not msgid:
		return "no-message-id"
	s = msgid.strip().strip("<>").replace("/", "_")
	s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
	return s[:180]


def _ensure_dir(p: Path):
	p.mkdir(parents=True, exist_ok=True)


def _parse_date(msg) -> tuple[str, str]:
	# returns (date_only, iso_localish)
	raw = msg.get("Date", "")
	try:
		dt = email.utils.parsedate_to_datetime(raw)
		iso = dt.isoformat()
		date_only = dt.date().isoformat()
		return date_only, iso
	except Exception:
		return "", ""


def _get_header(msg, name: str) -> str:
	v = msg.get(name, "")
	return str(v)


def _gmail_service():
	if not TOKEN_PATH.exists():
		print("Gmail token missing — running gmail_auth bootstrap")
		from handlers import gmail_auth
		gmail_auth.main()

	if not TOKEN_PATH.exists():
		raise SystemExit(f"Failed to obtain Gmail token at {TOKEN_PATH}")

	creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
	return build("gmail", "v1", credentials=creds)


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
	# yields (filename, bytes, content_type)
	for part in eml_msg.walk():
		if part.get_content_maintype() == "multipart":
			continue

		content_disposition = str(part.get("Content-Disposition") or "")
		if "attachment" not in content_disposition.lower():
			# exclude inline images etc.
			continue

		filename = part.get_filename()
		if not filename:
			ext = (part.get_content_subtype() or "bin").lower()
			filename = f"attachment.{ext}"

		data = part.get_payload(decode=True)
		if not data:
			continue

		ctype = str(part.get_content_type() or "application/octet-stream")
		yield filename, data, ctype

def _remove_label(service, msg_id: str, label_id: str):
	service.users().messages().modify(
		userId="me",
		id=msg_id,
		body={"removeLabelIds": [label_id]},
	).execute()

def main():
	service = _gmail_service()
	label_id = _get_label_id(service, LABEL_NAME)
	msg_ids = _list_message_ids(service, label_id, MAX_MESSAGES_PER_RUN)

	if not msg_ids:
		print("No messages to ingest.")
		return

	pl = PaperlessClient()

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

		custom_fields = {
			"Email Message-ID": render_result.message_id or message_id or "",
			"Email Archive Path": (str(eml_path)[-128:]),
			"Email Subject": render_result.subject or subject or "",
			"Email From": render_result.from_ or from_ or "",
			"Email To": render_result.to or to_ or "",
			"Email Date": email_date or "",
			"Email Is Parent": True,
		}

		existing_parent = pl.find_email_parent_by_message_id(custom_fields.get("Email Message-ID", ""))
		if existing_parent:
			parent_id = int(existing_parent["id"])
			print(f"Reusing existing email parent: parent_id={parent_id}")
		else:
			parent_task_id = pl.upload_document(
				file_path=pdf_path,
				title=parent_title,
			)
			print(f"Uploaded email parent task: {parent_title} | task_id={parent_task_id} | {pdf_path}")

			parent_id = pl.wait_for_task_document_id(parent_task_id, timeout_seconds=240)

			pl.set_tags_by_name(parent_id, ["email", "email-parent"])
			pl.set_custom_fields_by_name(parent_id, custom_fields)

			print(f"Email parent ready: parent_id={parent_id}")

		attach_dir = archive_dir / f"{safe_id}_attachments"
		_ensure_dir(attach_dir)

		for (fname, blob, ctype) in _iter_attachments(eml):
			# write file
			out_path = attach_dir / fname
			if out_path.exists():
				# avoid overwrite collisions
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

			# upload to Paperless (let Paperless detect mime)
			child_task_id = pl.upload_document(
				file_path=out_path,
				title=fname,
			)

			child_id, was_dup = pl.wait_for_task_document_id_and_status(child_task_id, timeout_seconds=240)

			# tag + custom field
			pl.set_tags_by_name(child_id, ["email", "email-attachment"])
			pl.set_custom_fields_by_name(child_id, {
				"Email Parent Doc ID": parent_id,
				"Email Message-ID": custom_fields.get("Email Message-ID", ""),
				"Email Date": custom_fields.get("Email Date", ""),
				"Email From": custom_fields.get("Email From", ""),
				"Email To": custom_fields.get("Email To", ""),
				"Email Subject": custom_fields.get("Email Subject", ""),
				"Email Archive Path": custom_fields.get("Email Archive Path", ""),
				"Email Is Parent": False,
			})

			if was_dup:
				print(f"Attachment reused: {fname} | child_id={child_id} | parent_id={parent_id}")
			else:
				print(f"Attachment uploaded: {fname} | child_id={child_id} | parent_id={parent_id}")

		_remove_label(service, mid, label_id)
		print(f"Label removed: {mid}")

		# NOTE: attachment upload + pl.set_parent(child_id, parent_id) will be added next step.

if __name__ == "__main__":
	main()