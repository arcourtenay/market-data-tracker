"""Ingests management-change events (Form 8-K, Item 5.02) for SEC-listed companies.

Item 5.02 covers the departure/election of directors and officers, so it's
the standard structured signal for "management changes" in EDGAR data.

Usage:
    python -m app.ingest                # full run, all companies
    python -m app.ingest --limit 25      # only the first 25 companies (testing)
"""

import argparse
import sys
from datetime import date, datetime

from sqlalchemy.orm import Session

from .database import SessionLocal, ensure_schema
from .models import Company, ManagementChangeEvent
from .sec_client import SecClient, build_filing_url

MANAGEMENT_CHANGE_ITEM = "5.02"
TARGET_FORM_PREFIX = "8-K"


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


def _ingest_company_filings(db: Session, client: SecClient, cik10: str, ticker: str | None) -> int:
    submissions = client.get_submissions(cik10)
    name = submissions.get("name") or ticker or cik10
    sic = submissions.get("sic")
    sic_description = submissions.get("sicDescription")

    company = _upsert_company(db, cik10, name, ticker, sic, sic_description)

    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    items_list = recent.get("items", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    primary_documents = recent.get("primaryDocument", [])

    new_events = 0
    for idx, form in enumerate(forms):
        if not form.startswith(TARGET_FORM_PREFIX):
            continue
        items = items_list[idx] if idx < len(items_list) else ""
        if MANAGEMENT_CHANGE_ITEM not in [i.strip() for i in items.split(",")]:
            continue

        accession_no = accession_numbers[idx]
        exists = (
            db.query(ManagementChangeEvent)
            .filter(ManagementChangeEvent.accession_no == accession_no)
            .one_or_none()
        )
        if exists:
            continue

        primary_document = primary_documents[idx] if idx < len(primary_documents) else None
        event = ManagementChangeEvent(
            company_id=company.id,
            accession_no=accession_no,
            form_type=form,
            items=items,
            filing_date=_parse_date(filing_dates[idx]),
            report_date=_parse_date(report_dates[idx] if idx < len(report_dates) else None),
            primary_document=primary_document,
            filing_url=build_filing_url(cik10, accession_no, primary_document),
        )
        db.add(event)
        new_events += 1

    return new_events


def run(limit: int | None = None) -> None:
    ensure_schema()

    client = SecClient()
    tickers_data = client.get_company_tickers()
    companies = list(tickers_data.values())
    if limit:
        companies = companies[:limit]

    total = len(companies)
    total_new_events = 0

    with SessionLocal() as db:
        for idx, entry in enumerate(companies, start=1):
            cik10 = str(entry["cik_str"]).zfill(10)
            ticker = entry.get("ticker")
            try:
                new_events = _ingest_company_filings(db, client, cik10, ticker)
                total_new_events += new_events
                db.commit()
            except Exception as exc:  # noqa: BLE001 - keep ingesting other companies
                db.rollback()
                print(f"  [warn] {ticker or cik10}: {exc}", file=sys.stderr)

            if idx % 50 == 0 or idx == total:
                print(f"  processed {idx}/{total} companies, {total_new_events} new events so far")

    print(f"Done. {total_new_events} new management-change events ingested.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N companies (for testing)")
    args = parser.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
