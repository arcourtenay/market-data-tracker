"""Ingests Form 10-K and 10-Q filings (including amendments) from SEC EDGAR's
daily index, for every SEC reporting company.

Like ingest_director_buys.py (and unlike ingest.py's SPAC/IPO detection),
this is a pure rolling feed: every 10-K/10-Q is inherently relevant, so
there's no per-company full-history scan needed - just SEC's daily index,
which already gives us the filer's CIK, name, form type, and accession
number directly. The only extra lookup is a single one-time fetch of SEC's
full ticker map, used to attach a ticker (for the market-cap filter) to
newly-seen companies without a per-company API call each.

Usage:
    python -m app.ingest_financial_results                  # last 3 days
    python -m app.ingest_financial_results --days-back 14    # last 14 days
"""

import argparse
import sys
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .database import SessionLocal, ensure_schema
from .ingest import _upsert_company
from .models import FinancialResultEvent
from .sec_client import SecClient

CANDIDATE_FORM_PREFIXES = ("10-K", "10-Q")


def _build_ticker_map(client: SecClient) -> dict[str, str]:
    tickers_data = client.get_company_tickers()
    return {str(entry["cik_str"]).zfill(10): entry["ticker"] for entry in tickers_data.values() if entry.get("ticker")}


def _ingest_one_filing(
    db: Session, cik10: str, name: str, form: str, accession_no: str, filing_date: date, ticker_map: dict[str, str]
) -> int:
    exists = db.query(FinancialResultEvent).filter(FinancialResultEvent.accession_no == accession_no).one_or_none()
    if exists:
        return 0

    company = _upsert_company(db, cik10, name, ticker_map.get(cik10), None, None)

    cik_no_zeros = str(int(cik10))
    accession_nodash = accession_no.replace("-", "")
    filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_nodash}/{accession_no}-index.htm"

    db.add(
        FinancialResultEvent(
            company_id=company.id,
            accession_no=accession_no,
            form_type=form,
            filing_date=filing_date,
            filing_url=filing_url,
        )
    )
    return 1


def run(days_back: int = 3) -> None:
    ensure_schema()
    client = SecClient()
    ticker_map = _build_ticker_map(client)

    total_checked = 0
    total_new_events = 0

    with SessionLocal() as db:
        for offset in range(days_back):
            day = date.today() - timedelta(days=offset)
            entries = [e for e in client.get_daily_index(day) if e["form"].startswith(CANDIDATE_FORM_PREFIXES)]
            print(f"{day}: {len(entries)} Form 10-K/10-Q filing(s)")

            for entry in entries:
                accession_no = entry["filename"].rsplit("/", 1)[-1].removesuffix(".txt")
                total_checked += 1
                try:
                    total_new_events += _ingest_one_filing(
                        db, entry["cik10"], entry["name"], entry["form"], accession_no, day, ticker_map
                    )
                    db.commit()
                except Exception as exc:  # noqa: BLE001 - keep ingesting the rest of the day's filings
                    db.rollback()
                    print(f"  [warn] {entry['name']} ({accession_no}): {exc}", file=sys.stderr)

                if total_checked % 500 == 0:
                    print(f"  checked {total_checked} filing(s), {total_new_events} new so far")

    print(f"Done. Checked {total_checked} filing(s), {total_new_events} new financial result event(s) ingested.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days-back", type=int, default=3, help="How many recent days to check (default 3)")
    args = parser.parse_args()
    run(days_back=args.days_back)


if __name__ == "__main__":
    main()
