from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import email
from email import policy
from email.message import Message
from email.utils import parsedate_to_datetime
from io import BytesIO

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

import html2text
from bs4 import BeautifulSoup
from PIL import Image


@dataclass
class InlineImage:
	cid: str
	mime: str
	data: bytes


@dataclass
class EmailRenderResult:
	subject: str
	from_: str
	to: str
	date_iso: str
	message_id: str
	body_text: str
	inline_images: List[InlineImage]


def _safe_str(v: Optional[str]) -> str:
	if v is None:
		return ""
	return str(v).strip()


def _parse_date_iso(raw_date: str) -> str:
	raw_date = _safe_str(raw_date)
	if not raw_date:
		return ""
	try:
		dt = parsedate_to_datetime(raw_date)
		if dt is None:
			return ""
		if dt.tzinfo is None:
			return dt.replace(tzinfo=None).isoformat()
		return dt.isoformat()
	except Exception:
		return ""


def _cid_norm(v: str) -> str:
	v = _safe_str(v)
	v = v.strip().strip("<>").strip()
	return v

def _collect_inline_images(msg: Message) -> Dict[str, InlineImage]:
	out: Dict[str, InlineImage] = {}
	if not msg.is_multipart():
		return out

	for part in msg.walk():
		if part.get_content_maintype() == "multipart":
			continue

		ctype = _safe_str(part.get_content_type()).lower()
		if not ctype.startswith("image/"):
			continue

		cid_raw = _safe_str(part.get("Content-ID"))
		cid = _cid_norm(cid_raw)
		if not cid:
			continue

		try:
			data = part.get_payload(decode=True)
		except Exception:
			data = None
		if not data:
			continue

		img = InlineImage(cid=cid, mime=ctype, data=data)

		# Index by full CID and also by the local part (before '@') because HTML often uses only that.
		out[cid] = img
		if "@" in cid:
			out[cid.split("@", 1)[0]] = img

	return out

def _get_best_body(msg: Message) -> Tuple[str, str, List[str], Dict[str, InlineImage]]:
	inline_map = _collect_inline_images(msg)

	text_part = None
	html_part = None

	if msg.is_multipart():
		for part in msg.walk():
			if part.get_content_maintype() == "multipart":
				continue
			disp = _safe_str(part.get("Content-Disposition"))
			if disp.lower().startswith("attachment"):
				continue

			ctype = _safe_str(part.get_content_type()).lower()
			try:
				payload = part.get_content()
			except Exception:
				try:
					payload = part.get_payload(decode=True)
					if payload is None:
						continue
					charset = part.get_content_charset() or "utf-8"
					payload = payload.decode(charset, errors="replace")
				except Exception:
					continue

			if ctype == "text/plain" and isinstance(payload, str) and text_part is None:
				text_part = payload
			elif ctype == "text/html" and isinstance(payload, str) and html_part is None:
				html_part = payload
	else:
		ctype = _safe_str(msg.get_content_type()).lower()
		try:
			payload = msg.get_content()
		except Exception:
			payload = msg.get_payload(decode=True)
			if payload is None:
				payload = b""
			charset = msg.get_content_charset() or "utf-8"
			payload = payload.decode(charset, errors="replace")
		if ctype == "text/html":
			html_part = payload if isinstance(payload, str) else ""
		else:
			text_part = payload if isinstance(payload, str) else ""

	inline_order: List[str] = []

	if html_part:
		try:
			soup = BeautifulSoup(html_part, "html.parser")

			for img in soup.find_all("img"):
				src = _safe_str(img.get("src"))
				if src.lower().startswith("cid:"):
					cid = _cid_norm(src[4:])
					if cid:
						inline_order.append(cid)
						img.replace_with(soup.new_string(f"\n<<INLINE_IMAGE:{cid}>>\n"))

			html2 = str(soup)

			h = html2text.HTML2Text()
			h.ignore_links = False
			h.ignore_images = True
			h.body_width = 0
			txt = h.handle(html2)
			txt = txt.replace("\r\n", "\n").replace("\r", "\n").strip()
			return ("html", txt, inline_order, inline_map)
		except Exception:
			pass

	if text_part:
		txt = text_part.replace("\r\n", "\n").replace("\r", "\n").strip()
		return ("text", txt, inline_order, inline_map)

	return ("none", "", inline_order, inline_map)


def parse_eml(eml_path: Path) -> EmailRenderResult:
	raw = eml_path.read_bytes()
	msg = email.message_from_bytes(raw, policy=policy.default)

	subject = _safe_str(msg.get("Subject"))
	from_ = _safe_str(msg.get("From"))
	to = _safe_str(msg.get("To"))
	date_raw = _safe_str(msg.get("Date"))
	date_iso = _parse_date_iso(date_raw)
	message_id = _safe_str(msg.get("Message-ID"))

	_, body_text, inline_order, inline_map = _get_best_body(msg)
	inline_images = []
	for c in inline_order:
		c = _cid_norm(c)
		if c in inline_map:
			inline_images.append(inline_map[c])
			continue
		# fallback: if HTML has local part, but map only has full cid, pick first match
		if "@" not in c:
			for k in inline_map.keys():
				if isinstance(k, str) and k.startswith(c + "@"):
					inline_images.append(inline_map[k])
					break

	return EmailRenderResult(
		subject=subject,
		from_=from_,
		to=to,
		date_iso=date_iso,
		message_id=message_id,
		body_text=body_text,
		inline_images=inline_images,
	)


def render_email_pdf(eml_path: Path, pdf_path: Path) -> EmailRenderResult:
	res = parse_eml(eml_path)

	pdf_path.parent.mkdir(parents=True, exist_ok=True)

	c = canvas.Canvas(str(pdf_path), pagesize=LETTER)
	width, height = LETTER

	left = 54
	right = width - 54
	top = height - 54
	bottom = 54

	y = top
	line_h = 14

	def new_page():
		nonlocal y
		c.showPage()
		y = top

	def draw_wrapped_line(s: str) -> None:
		nonlocal y
		if s is None:
			s = ""
		max_w = right - left
		words = s.replace("\t", "    ").split(" ")
		cur = ""
		for w in words:
			try_line = (cur + " " + w).strip()
			if c.stringWidth(try_line, "Helvetica", 11) <= max_w:
				cur = try_line
			else:
				c.setFont("Helvetica", 11)
				c.drawString(left, y, cur)
				y -= line_h
				cur = w
				if y <= bottom:
					new_page()
		if cur:
			c.setFont("Helvetica", 11)
			c.drawString(left, y, cur)
			y -= line_h
			if y <= bottom:
				new_page()

	def draw_inline_image(img: InlineImage) -> None:
		nonlocal y
		try:
			im = Image.open(BytesIO(img.data))
			im.load()
			w, h = im.size
			if w <= 0 or h <= 0:
				return

			max_w = right - left
			max_h = (y - bottom) - 24
			if max_h < 100:
				new_page()
				max_h = (y - bottom) - 24

			scale = min(max_w / float(w), max_h / float(h), 1.0)
			dw = float(w) * scale
			dh = float(h) * scale

			y -= 12
			reader = ImageReader(BytesIO(img.data))
			c.drawImage(reader, left, y - dh, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
			y -= (dh + 12)

			if y <= bottom:
				new_page()
		except Exception:
			draw_wrapped_line(f"[Inline image omitted: {img.cid}]")

	header_lines = [
		f"Subject: {res.subject}",
		f"From: {res.from_}",
		f"To: {res.to}",
		f"Date: {res.date_iso}",
		f"Message-ID: {res.message_id}",
		"",
	]

	for hl in header_lines:
		draw_wrapped_line(hl)

	body = res.body_text or ""
	inline_by_cid = {i.cid: i for i in res.inline_images}

	if body:
		for raw_line in body.split("\n"):
			line = raw_line.strip()
			if "<<INLINE_IMAGE:" in line:
				cid = line
				cid = cid.replace("<<INLINE_IMAGE:", "")
				cid = cid.replace(">>", "")
				cid = cid.replace("*", "")
				cid = cid.replace("<", "")
				cid = cid.replace(">", "")
				cid = cid.strip()
				cid = _cid_norm(cid)

				img = inline_by_cid.get(cid)
				if img:
					draw_inline_image(img)
				else:
					draw_wrapped_line(f"[Inline image missing: {cid}]")
				continue
			draw_wrapped_line(raw_line)

	c.save()
	return res