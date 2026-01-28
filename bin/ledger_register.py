import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json
import argparse
from ledger.db import LedgerDB
from ledger.register import process_event


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--events", required=True)
	args = parser.parse_args()

	db = LedgerDB("data/ledger.sqlite3")

	changed = 0
	processed = 0

	with open(args.events, "r", encoding="utf-8") as f:
		for line in f:
			event = json.loads(line)
			before = db.document_count()
			process_event(db, event)
			after = db.document_count()
			if after != before:
				changed += abs(after - before)
			processed += 1

	print(f"Processed events: {processed}")
	print(f"Documents changed: {changed}")


if __name__ == "__main__":
	main()
