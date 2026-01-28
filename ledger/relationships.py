import uuid
from datetime import datetime, timezone


def utcnow():
	return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upsert_relationship(
	db,
	*,
	relationship_type,
	src_type,
	src_id,
	dst_type,
	dst_id,
	created_by,
):
	now = utcnow()
	rid = str(uuid.uuid4())

	db.con.execute(
		"""
		INSERT OR IGNORE INTO relationships
		(relationship_id, relationship_type, src_type, src_id, dst_type, dst_id, created_by, created_at, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(rid, relationship_type, src_type, src_id, dst_type, dst_id, created_by, now, now),
	)
	db.con.commit()
