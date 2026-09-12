"""Fills in ManagementChangeEvent.people for rows not yet processed, using Claude.

Run after app.ingest has added new filings. Safe to re-run: only processes rows
where `people IS NULL` (never attempted), so it naturally covers new filings
without re-spending on ones already done.

Usage:
    python -m app.extract_people                 # process every unprocessed row
    python -m app.extract_people --limit 25       # only the first 25 (testing)
"""

import argparse
import sys

from .database import SessionLocal, ensure_schema
from .models import ManagementChangeEvent
from .name_extraction import PeopleExtractor, html_to_text
from .sec_client import SecClient


def run(limit: int | None = None) -> None:
    ensure_schema()

    client = SecClient()
    extractor = PeopleExtractor()

    with SessionLocal() as db:
        query = (
            db.query(ManagementChangeEvent)
            .filter(ManagementChangeEvent.people.is_(None))
            .order_by(ManagementChangeEvent.filing_date.desc())
        )
        if limit:
            query = query.limit(limit)
        events = query.all()

        total = len(events)
        print(f"{total} filing(s) to process")

        for idx, event in enumerate(events, start=1):
            try:
                html = client.get_text(event.filing_url)
                text = html_to_text(html)
                event.people = extractor.extract(text)
                db.commit()
            except Exception as exc:  # noqa: BLE001 - keep going, leave this row for the next run
                db.rollback()
                print(f"  [warn] event {event.id} ({event.accession_no}): {exc}", file=sys.stderr)

            if idx % 25 == 0 or idx == total:
                print(f"  processed {idx}/{total}")

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N unprocessed rows")
    args = parser.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
