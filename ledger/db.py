import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any


def utcnow() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class LedgerDB:
        def __init__(self, path: str):
                self.con = sqlite3.connect(path)
                self.con.row_factory = sqlite3.Row
                self._init()

        def _init(self) -> None:
                c = self.con.cursor()

                # Documents (expanded schema; matches migrations)
                c.execute(
                        """
                        CREATE TABLE IF NOT EXISTS documents (
                                document_id TEXT PRIMARY KEY,
                                source_type TEXT NOT NULL,
                                source_locator TEXT NOT NULL,
                                kind TEXT NOT NULL,
                                created_at TEXT NOT NULL,
                                updated_at TEXT NOT NULL,

                                source_fingerprint TEXT,
                                roles_json TEXT NOT NULL DEFAULT '[]',
                                entity_id TEXT,

                                title TEXT,
                                original_filename TEXT,
                                mime_type TEXT,
                                byte_size INTEGER,
                                sha256 TEXT,

                                UNIQUE(source_type, source_locator)
                        )
                        """
                )
                c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_source_fingerprint ON documents (source_fingerprint)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_documents_entity_id ON documents (entity_id)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_documents_kind ON documents (kind)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents (sha256)")

                # Relationships
                c.execute(
                        """
                        CREATE TABLE IF NOT EXISTS relationships (
                                relationship_id TEXT PRIMARY KEY,
                                relationship_type TEXT NOT NULL,
                                src_type TEXT NOT NULL,
                                src_id TEXT NOT NULL,
                                dst_type TEXT NOT NULL,
                                dst_id TEXT NOT NULL,
                                created_by TEXT NOT NULL,
                                created_at TEXT NOT NULL,
                                updated_at TEXT NOT NULL,
                                UNIQUE(relationship_type, src_type, src_id, dst_type, dst_id)
                        )
                        """
                )

                # Transactions + links are migration-defined; keep minimal safety for fresh DBs only.
                c.execute(
                        """
                        CREATE TABLE IF NOT EXISTS transactions (
                                txn_id TEXT PRIMARY KEY,
                                source_type TEXT NOT NULL,
                                source_locator TEXT NOT NULL,
                                amount REAL NOT NULL,
                                currency TEXT NOT NULL,
                                txn_date TEXT NOT NULL,
                                description TEXT NULL,
                                counterparty TEXT NULL,
                                account_id TEXT NULL,
                                entity_id TEXT NULL,
                                status TEXT NOT NULL DEFAULT 'posted',
                                created_at TEXT NOT NULL,
                                updated_at TEXT NOT NULL,
                                UNIQUE(source_type, source_locator)
                        )
                        """
                )
                c.execute(
                        """
                        CREATE TABLE IF NOT EXISTS document_transactions (
                                id TEXT PRIMARY KEY,
                                document_id TEXT NOT NULL,
                                txn_id TEXT NOT NULL,
                                link_type TEXT NOT NULL,
                                confidence REAL NOT NULL DEFAULT 1.0,
                                created_by TEXT NOT NULL,
                                evidence_json TEXT NOT NULL DEFAULT '{}',
                                created_at TEXT NOT NULL,
                                UNIQUE(document_id, txn_id, link_type)
                        )
                        """
                )

                self.con.commit()

        # ---------- Documents ----------

        def find_document(self, source_type: str, source_locator: str):
                return self.con.execute(
                        "SELECT * FROM documents WHERE source_type=? AND source_locator=?",
                        (source_type, source_locator),
                ).fetchone()

        def find_document_by_id(self, document_id: str):
                return self.con.execute(
                        "SELECT * FROM documents WHERE document_id=?",
                        (document_id,),
                ).fetchone()

        def find_document_by_fingerprint(self, source_fingerprint: str):
                return self.con.execute(
                        "SELECT * FROM documents WHERE source_fingerprint=?",
                        (source_fingerprint,),
                ).fetchone()

        def insert_document(
                self,
                *,
                document_id: str,
                source_type: str,
                source_locator: str,
                kind: str,
                created_at: str,
                updated_at: str,
                source_fingerprint: Optional[str] = None,
                roles_json: str = "[]",
                entity_id: Optional[str] = None,
                title: Optional[str] = None,
                original_filename: Optional[str] = None,
                mime_type: Optional[str] = None,
                byte_size: Optional[int] = None,
                sha256: Optional[str] = None,
        ) -> None:
                self.con.execute(
                        """
                        INSERT INTO documents (
                                document_id, source_type, source_locator, kind,
                                created_at, updated_at,
                                source_fingerprint, roles_json, entity_id,
                                title, original_filename, mime_type, byte_size, sha256
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                                document_id,
                                source_type,
                                source_locator,
                                kind,
                                created_at,
                                updated_at,
                                source_fingerprint,
                                roles_json,
                                entity_id,
                                title,
                                original_filename,
                                mime_type,
                                byte_size,
                                sha256,
                        ),
                )
                self.con.commit()

        def update_document(self, document_id: str, updates: Dict[str, Any]) -> None:
                if not updates:
                        return
                sets = ", ".join(f"{k}=:{k}" for k in updates.keys())
                updates = dict(updates)
                updates["document_id"] = document_id
                self.con.execute(
                        f"UPDATE documents SET {sets} WHERE document_id=:document_id",
                        updates,
                )
                self.con.commit()

        def document_count(self) -> int:
                return self.con.execute("SELECT count(*) FROM documents").fetchone()[0]

        # ---------- Transactions ----------

        def find_transaction_by_source(self, source_type: str, source_locator: str):
                return self.con.execute(
                        """
                        SELECT * FROM transactions
                        WHERE source_type=? AND source_locator=?
                        """,
                        (source_type, source_locator),
                ).fetchone()

        def insert_transaction(self, row: dict) -> None:
                self.con.execute(
                        """
                        INSERT INTO transactions (
                                txn_id, source_type, source_locator,
                                amount, currency, txn_date,
                                description, counterparty,
                                account_id, entity_id,
                                status, created_at, updated_at
                        )
                        VALUES (
                                :txn_id, :source_type, :source_locator,
                                :amount, :currency, :txn_date,
                                :description, :counterparty,
                                :account_id, :entity_id,
                                :status, :created_at, :updated_at
                        )
                        """,
                        row,
                )
                self.con.commit()

        def update_transaction(self, txn_id: str, updates: dict) -> None:
                sets = ", ".join(f"{k}=:{k}" for k in updates.keys())
                updates["txn_id"] = txn_id
                self.con.execute(
                        f"UPDATE transactions SET {sets} WHERE txn_id=:txn_id",
                        updates,
                )
                self.con.commit()

        def upsert_document_transaction_link(self, row: dict) -> bool:
                cur = self.con.execute(
                        """
                        INSERT OR IGNORE INTO document_transactions (
                                id, document_id, txn_id,
                                link_type, confidence,
                                created_by, evidence_json, created_at
                        )
                        VALUES (
                                :id, :document_id, :txn_id,
                                :link_type, :confidence,
                                :created_by, :evidence_json, :created_at
                        )
                        """,
                        row,
                )
                self.con.commit()
                return cur.rowcount == 1
