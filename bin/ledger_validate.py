import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ledger.validate import format_report, validate_ledger


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Validate ledger invariants.")
	parser.add_argument("--limit", type=int, default=10, help="Max violations to list per category.")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	db_path = ROOT / "data" / "ledger.sqlite3"
	docs_dir = ROOT / "state" / "docs"

	if not db_path.exists():
		print(f"ERROR: missing database at {db_path}")
		return 1
	if not docs_dir.exists():
		print(f"ERROR: missing docs directory at {docs_dir}")
		return 1

	try:
		report = validate_ledger(db_path, docs_dir, limit=args.limit)
	except sqlite3.Error as exc:
		print(f"ERROR: unable to open ledger database: {exc}")
		return 1
	except Exception as exc:
		print(f"ERROR: validation failed: {exc}")
		return 1

	print(format_report(report, limit=args.limit))
	if report.violations:
		return 2
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
