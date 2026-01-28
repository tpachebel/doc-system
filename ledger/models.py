from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class FingerprintInputs:
	source_type: str
	source_locator: str
	sha256: Optional[str] = None
	byte_size: Optional[int] = None
	mime_type: Optional[str] = None
	message_id: Optional[str] = None
	attachment_part_id: Optional[str] = None
	original_filename: Optional[str] = None
	received_date: Optional[str] = None
	subject: Optional[str] = None
	from_addr: Optional[str] = None


@dataclass
class DocumentUpsert:
	source_type: str
	source_locator: str
	source_fingerprint: str
	kind: str
	roles: List[str]
	entity_id: Optional[str] = None
	entity_candidates: List[Dict[str, Any]] = None
	title: Optional[str] = None
	original_filename: Optional[str] = None
	mime_type: Optional[str] = None
	byte_size: Optional[int] = None
	sha256: Optional[str] = None

	def normalized(self) -> "DocumentUpsert":
		self.roles = self.roles or []
		self.entity_candidates = self.entity_candidates or []
		return self


RelationshipKey = Tuple[str, str, str, str, str]
# (relationship_type, src_type, src_id, dst_type, dst_id)
