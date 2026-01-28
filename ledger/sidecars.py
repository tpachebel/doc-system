import json
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import os
import time


def utcnow():
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, content: str):
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = None
        try:
                with tempfile.NamedTemporaryFile(
                        "w",
                        encoding="utf-8",
                        delete=False,
                        dir=str(path.parent),
                        newline="\n",
                ) as tf:
                        tf.write(content)
                        tmp_path = Path(tf.name).resolve()

                # Windows/Nextcloud/AV can temporarily lock the destination.
                # Retry the rename/replace a few times with short backoff.
                last_err = None
                for i in range(12):
                        try:
                                os.replace(str(tmp_path), str(path))
                                return
                        except PermissionError as e:
                                last_err = e
                                time.sleep(0.1 + (i * 0.15))
                                continue

                raise last_err  # noqa: B904

        finally:
                # If we failed before replace, clean up temp file.
                try:
                        if tmp_path and tmp_path.exists():
                                tmp_path.unlink(missing_ok=True)
                except Exception:
                        pass


# ---------- Document sidecars (unchanged semantics) ----------

def write_sidecar(document_id, *, kind, source_type, source_locator, event, attachment):
        path = Path("state/docs") / f"{document_id}.json"
        now = utcnow()

        data = {
                "document_id": document_id,
                "schema_version": 1,
                "kind": kind,
                "sources": {
                        "source_type": source_type,
                        "source_locator": source_locator,
                },
                "ingest": {
                        "created_at": now,
                        "event": event,
                },
        }

        if attachment:
                data["attachment"] = attachment

        if event and isinstance(event, dict):
                # Preserve known artifact pointers if present
                payload = event.get("payload", {})
                if isinstance(payload, dict):
                        if "archive_pdf" in payload:
                                data.setdefault("artifacts", {})["rendered_pdf"] = {"path": payload["archive_pdf"]}
                        if "archive_eml" in payload:
                                data.setdefault("artifacts", {})["original_eml"] = {"path": payload["archive_eml"]}

        serialized = json.dumps(data, indent=2, sort_keys=True) + "\n"
        _atomic_write(path, serialized)


# ---------- Transaction sidecars ----------

def write_transaction_sidecar(txn: dict, *, links=None, evidence=None):
        txn_id = txn["txn_id"]
        path = Path("state/txns") / f"{txn_id}.json"

        data = {
                "schema_version": 1,
                "txn": txn,
                "sources": {
                        "source_type": txn["source_type"],
                        "source_locator": txn["source_locator"],
                },
        }

        if links is not None:
                data["links"] = sorted(
                        links,
                        key=lambda x: (x["document_id"], x["link_type"], x["created_by"]),
                )

        if evidence is not None:
                data["evidence"] = sorted(
                        evidence,
                        key=lambda x: (
                                x["document_id"],
                                x.get("page"),
                                x.get("snippet"),
                        ),
                )

        serialized = json.dumps(data, indent=2, sort_keys=True) + "\n"

        if path.exists() and path.read_text(encoding="utf-8") == serialized:
                return False

        _atomic_write(path, serialized)
        return True
