"""Ingests SPAC lifecycle events from SEC EDGAR for every SEC-listed company:

  - SPAC IPOs: Form 424B4 (final IPO prospectus) filed by a company with SIC
    6770 ("Blank Checks" - the SEC's own classification for SPACs).
  - De-SPAC merger completions: Form 8-K, Item 5.06 ("Change in Shell Company
    Status") - filed when a shell company like a SPAC completes its merger
    and becomes an operating business.

Two ways to find candidate companies to check:

  - Daily index (default, fast): SEC publishes one file per day listing every
    filing submitted that day, across all ~10,000+ filers. We only need to
    check the companies that show up in it with a relevant form type - a few
    hundred, not ten thousand - so this finishes in minutes.
  - Full scan (--full, slow): walks every company in company_tickers.json and
    checks its full filing history. Useful for an occasional backfill (e.g.
    the first run, or to catch anything the daily index might have missed),
    but takes hours at SEC's request pace across 10,000+ companies.

Usage:
    python -m app.ingest                    # fast path, checks the last 3 days' filings
    python -m app.ingest --days-back 7       # fast path, last 7 days
    python -m app.ingest --full              # full scan, all companies
    python -m app.ingest --full --limit 25   # full scan, first 25 companies (testing)
"""

import argparse
import sys
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .database import SessionLocal, ensure_schema
from .models import Company, SpacEvent
from .sec_client import SecClient, build_filing_url

DESPAC_ITEM = "5.06"
SPAC_IPO_FORM = "424B4"
SPAC_IPO_SIC = "6770"
CANDIDATE_FORM_PREFIXES = ("8-K", "424B4")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _upsert_company(db: Session, cik10: str, name: str, ticker: str | None, sic: str | None, sic_description: str | None) -> Company:
    company = db.query(Company).filter(Company.cik == cik10).one_or_none()
    if company is None:
        company = Company(cik=cik10, name=name, ticker=ticker, sic=sic, sic_description=sic_description)
        db.add(company)
    else:
        company.name = name
        company.ticker = ticker or company.ticker
        company.sic = sic or company.sic
        company.sic_description = sic_description or company.sic_description
    db.flush()
    return company


def _ingest_company_filings(db: Session, client: SecClient, cik10: str, ticker: str | None = None) -> int:
    submissions = client.get_submissions(cik10)
    name = submissions.get("name") or ticker or cik10
    sic = submissions.get("sic")
    sic_description = submissions.get("sicDescription")
    ticker = (submissions.get("tickers") or [None])[0] or ticker

    company = _upsert_company(db, cik10, name, ticker, sic, sic_description)

    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    items_list = recent.get("items", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    primary_documents = recent.get("primaryDocument", [])

    new_spac_events = 0

    for idx, form in enumerate(forms):
        accession_no = accession_numbers[idx]
        items = items_list[idx] if idx < len(items_list) else ""
        item_list = [i.strip() for i in items.split(",") if i.strip()]
        primary_document = primary_documents[idx] if idx < len(primary_documents) else None
        filing_date = _parse_date(filing_dates[idx])
        report_date = _parse_date(report_dates[idx] if idx < len(report_dates) else None)
        filing_url = build_filing_url(cik10, accession_no, primary_document)

        stage = None
        if form.startswith("8-K") and DESPAC_ITEM in item_list:
            stage = "merger_completed"
        elif form == SPAC_IPO_FORM and sic == SPAC_IPO_SIC:
            stage = "ipo"

        if stage:
            exists = db.query(SpacEvent).filter(SpacEvent.accession_no == accession_no).one_or_none()
            if not exists:
                db.add(
                    SpacEvent(
                        company_id=company.id,
                        accession_no=accession_no,
                        form_type=form,
                        items=items,
                        stage=stage,
                        filing_date=filing_date,
                        report_date=report_date,
                        primary_document=primary_document,
                        filing_url=filing_url,
                    )
                )
                new_spac_events += 1

    return new_spac_events


def _process_companies(client: SecClient, ciks: list[tuple[str, str | None]]) -> None:
    """ciks: list of (cik10, ticker-or-None) to check. Shared by both entry points."""
    total = len(ciks)
    total_new_spac_events = 0

    with SessionLocal() as db:
        for idx, (cik10, ticker) in enumerate(ciks, start=1):
            try:
                new_spac_events = _ingest_company_filings(db, client, cik10, ticker)
                total_new_spac_events += new_spac_events
                db.commit()
            except Exception as exc:  # noqa: BLE001 - keep ingesting other companies
                db.rollback()
                print(f"  [warn] {ticker or cik10}: {exc}", file=sys.stderr)

            if idx % 50 == 0 or idx == total:
                print(f"  processed {idx}/{total} companies, {total_new_spac_events} new SPAC events so far")

    print(f"Done. {total_new_spac_events} new SPAC events ingested.")


def run_daily_index(days_back: int = 3) -> None:
    """Fast path: only checks companies that filed something relevant in the
    last `days_back` days, per SEC's own daily index. Safe to overlap days
    across runs (all writes are dedupe-by-accession-number)."""
    ensure_schema()
    client = SecClient()

    candidate_ciks: dict[str, None] = {}
    for offset in range(days_back):
        day = date.today() - timedelta(days=offset)
        entries = client.get_daily_index(day)
        for entry in entries:
            if entry["form"].startswith(CANDIDATE_FORM_PREFIXES):
                candidate_ciks[entry["cik10"]] = None

    print(f"{len(candidate_ciks)} compan(ies) filed something relevant in the last {days_back} day(s)")
    _process_companies(client, [(cik, None) for cik in candidate_ciks])


def run_full_scan(limit: int | None = None) -> None:
    """Slow path: walks every company in company_tickers.json and checks its
    full filing history. For an occasional complete backfill - takes hours
    across all ~10,000+ SEC filers."""
    ensure_schema()
    client = SecClient()
    tickers_data = client.get_company_tickers()
    companies = list(tickers_data.values())
    if limit:
        companies = companies[:limit]

    ciks = [(str(entry["cik_str"]).zfill(10), entry.get("ticker")) for entry in companies]
    _process_companies(client, ciks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="Full scan of all SEC filers (slow, for backfills)")
    parser.add_argument("--days-back", type=int, default=3, help="Fast path: how many recent days to check (default 3)")
    parser.add_argument("--limit", type=int, default=None, help="Full scan only: cap on companies processed (testing)")
    args = parser.parse_args()

    if args.full:
        run_full_scan(limit=args.limit)
    else:
        run_daily_index(days_back=args.days_back)


if __name__ == "__main__":
    main()
