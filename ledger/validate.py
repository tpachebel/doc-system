from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


@dataclass
class Violation:
	category: str
	detail: str


@dataclass
class ValidationReport:
	required_tables: List[str]
	missing_tables: List[str] = field(default_factory=list)
	relationship_total: int = 0
	relationship_violations: List[Violation] = field(default_factory=list)
	sidecar_total: int = 0
	sidecar_violations: List[Violation] = field(default_factory=list)

	@property
	def violations(self) -> List[Violation]:
		return [
			*self._table_violations(),
			*self.relationship_violations,
			*self.sidecar_violations,
		]

	def _table_violations(self) -> List[Violation]:
		return [
			Violation("missing_table", f"required table missing: {name}")
			for name in self.missing_tables
		]


TYPE_TABLE_MAP: Dict[str, Tuple[str, str]] = {
	"document": ("documents", "document_id"),
	"transaction": ("transactions", "txn_id"),
	"txn": ("transactions", "txn_id"),
	"entity": ("entities", "entity_id"),
	"property": ("properties", "property_id"),
	"unit": ("units", "unit_id"),
	"policy": ("policies", "policy_id"),
}


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
	row = con.execute(
		"SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
		(table,),
	).fetchone()
	return row is not None


def _fetch_ids(con: sqlite3.Connection, table: str, column: str) -> set[str]:
	rows = con.execute(f"SELECT {column} FROM {table}").fetchall()
	return {row[0] for row in rows}


def _required_tables_present(con: sqlite3.Connection, tables: Iterable[str]) -> List[str]:
	missing = []
	for table in tables:
		if not _table_exists(con, table):
			missing.append(table)
	return missing


def validate_ledger(db_path: Path, docs_dir: Path, *, limit: int = 10) -> ValidationReport:
	required_tables = [
		"documents",
		"relationships",
		"transactions",
		"document_transactions",
	]

	uri = f"file:{db_path}?mode=ro"
	with sqlite3.connect(uri, uri=True) as con:
		report = ValidationReport(required_tables=required_tables)
		report.missing_tables = _required_tables_present(con, required_tables)
		if report.missing_tables:
			return report

		doc_ids = _fetch_ids(con, "documents", "document_id")
		rel_rows = con.execute(
			"SELECT relationship_id, src_type, src_id, dst_type, dst_id FROM relationships"
		).fetchall()
		report.relationship_total = len(rel_rows)

		cached_ids: Dict[Tuple[str, str], set[str]] = {}

		def ensure_ids(type_name: str) -> set[str] | None:
			mapping = TYPE_TABLE_MAP.get(type_name)
			if not mapping:
				return None
			table, column = mapping
			if not _table_exists(con, table):
				return None
			key = (table, column)
			if key not in cached_ids:
				cached_ids[key] = _fetch_ids(con, table, column)
			return cached_ids[key]

		for rel_id, src_type, src_id, dst_type, dst_id in rel_rows:
			for role, type_name, value in (
				("src", src_type, src_id),
				("dst", dst_type, dst_id),
			):
				id_set = ensure_ids(type_name)
				if id_set is None:
					report.relationship_violations.append(
						Violation(
							"relationship_missing_table",
							f"relationship {rel_id} {role} type '{type_name}' has no table",
						)
					)
					continue
				if value not in id_set:
					report.relationship_violations.append(
						Violation(
							"relationship_dangling",
							f"relationship {rel_id} {role} {type_name}:{value} missing",
						)
					)
				if len(report.relationship_violations) >= limit:
					break
			if len(report.relationship_violations) >= limit:
				break

		sidecars = list(docs_dir.glob("*.json"))
		report.sidecar_total = len(sidecars)
		for fp in sidecars:
			doc_id = fp.stem
			if doc_id not in doc_ids:
				report.sidecar_violations.append(
					Violation(
						"sidecar_missing_document",
						f"sidecar {fp.name} has no document row",
					)
				)
				if len(report.sidecar_violations) >= limit:
					break

		return report


def format_report(report: ValidationReport, *, limit: int = 10) -> str:
	lines = ["Ledger validation report"]
	required_total = len(report.required_tables)
	missing_total = len(report.missing_tables)
	if missing_total:
		lines.append(f"- Required tables: missing {missing_total}/{required_total}")
	else:
		lines.append(f"- Required tables: ok ({required_total}/{required_total})")
	lines.append(
		f"- Relationships: total {report.relationship_total}, violations {len(report.relationship_violations)}"
	)
	lines.append(
		f"- Sidecars: total {report.sidecar_total}, violations {len(report.sidecar_violations)}"
	)
	violations = report.violations
	lines.append(f"- Total violations: {len(violations)}")
	if violations:
		lines.append(f"\nViolations (showing first {min(limit, len(violations))}):")
		for idx, violation in enumerate(violations[:limit], start=1):
			lines.append(f"{idx}. {violation.category}: {violation.detail}")
	return "\n".join(lines)
