"""Ingests director open-market share sales from SEC Form 4 filings
(Statement of Changes in Beneficial Ownership).

Mirrors ingest_director_buys.py exactly, but for sales: unlike ingest.py's
SPAC/IPO detection (which scans each candidate company's FULL filing history
to find "earliest visible" events), this is a pure rolling feed: SEC's daily
index lists every Form 4 filed each day - we fetch and parse each one
directly (Form 4's ownership XML is fully structured, no text/LLM extraction
involved) and keep any qualifying transaction. There's no per-company history
to check, since a Form 4 always reports its own transaction date directly.

A transaction qualifies when:
  - the reporting owner has isDirector=true (officer-only or 10%-owner-only
    filers are excluded - this tracks directors specifically), and
  - the transaction is coded 'S' (open market sale) with a
    'D' (disposed) disposition - not gifts, dispositions to the issuer, or
    tax withholding.

Note: Form 4's daily-index entry is filed under the REPORTING OWNER's CIK,
not the issuer's - the issuer (company) is only known once the XML itself is
parsed, so the company upsert happens per-transaction rather than up front.

Usage:
    python -m app.ingest_director_sells                  # last 3 days
    python -m app.ingest_director_sells --days-back 14    # last 14 days
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .database import SessionLocal, ensure_schema
from .ingest import _upsert_company
from .models import DirectorSellEvent
from .sec_client import SecClient

SALE_CODE = "S"
DISPOSED_CODE = "D"


def _text(el: ET.Element | None, path: str) -> str | None:
    found = el.find(path) if el is not None else None
    return found.text.strip() if found is not None and found.text else None


def _is_true(value: str | None) -> bool:
    return value is not None and value.strip().lower() in ("1", "true")


def _find_ownership_xml(client: SecClient, cik_no_zeros: str, accession_nodash: str) -> ET.Element | None:
    """A Form 4 filing's structured XML has no consistent filename across
    filers (much like the 13F info table) - try every .xml file in the
    filing until one parses as an ownershipDocument."""
    index = client.get_json(f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_nodash}/index.json")
    xml_names = [item["name"] for item in index.get("directory", {}).get("item", []) if item["name"].endswith(".xml")]
    for name in xml_names:
        text = client.get_text(f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_nodash}/{name}")
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            continue
        if root.tag == "ownershipDocument":
            return root
    return None


def _ingest_one_form4(
    db: Session, client: SecClient, filer_cik10: str, accession_no: str, filing_date: date
) -> int:
    cik_no_zeros = str(int(filer_cik10))
    accession_nodash = accession_no.replace("-", "")
    root = _find_ownership_xml(client, cik_no_zeros, accession_nodash)
    if root is None:
        return 0

    owner = root.find("reportingOwner")
    if owner is None or not _is_true(_text(owner, "reportingOwnerRelationship/isDirector")):
        return 0

    owner_name = _text(owner, "reportingOwnerId/rptOwnerName") or "Unknown"
    officer_title = _text(owner, "reportingOwnerRelationship/officerTitle")

    issuer_cik = _text(root, "issuer/issuerCik")
    issuer_name = _text(root, "issuer/issuerName")
    issuer_ticker = _text(root, "issuer/issuerTradingSymbol")
    if not issuer_cik or not issuer_name:
        return 0
    issuer_cik10 = issuer_cik.zfill(10)

    filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_nodash}/{accession_no}-index.htm"

    new_events = 0
    for line_no, txn in enumerate(root.findall("nonDerivativeTable/nonDerivativeTransaction")):
        code = _text(txn, "transactionCoding/transactionCode")
        acquired_disposed = _text(txn, "transactionAmounts/transactionAcquiredDisposedCode/value")
        if code != SALE_CODE or acquired_disposed != DISPOSED_CODE:
            continue

        shares_str = _text(txn, "transactionAmounts/transactionShares/value")
        price_str = _text(txn, "transactionAmounts/transactionPricePerShare/value")
        txn_date_str = _text(txn, "transactionDate/value")
        if not shares_str or not price_str or not txn_date_str:
            continue
        shares, price = float(shares_str), float(price_str)
        if shares <= 0 or price <= 0:
            continue

        exists = (
            db.query(DirectorSellEvent)
            .filter(DirectorSellEvent.accession_no == accession_no, DirectorSellEvent.line_no == line_no)
            .one_or_none()
        )
        if exists:
            continue

        company = _upsert_company(db, issuer_cik10, issuer_name, issuer_ticker, None, None)
        db.add(
            DirectorSellEvent(
                company_id=company.id,
                accession_no=accession_no,
                line_no=line_no,
                reporting_owner_name=owner_name,
                officer_title=officer_title,
                # Take just the YYYY-MM-DD prefix - some filers' XML appends a
                # spurious timezone suffix directly onto the date (e.g. "2026-09-14-05:00"),
                # which a strict %Y-%m-%d parse chokes on.
                transaction_date=datetime.strptime(txn_date_str[:10], "%Y-%m-%d").date(),
                filing_date=filing_date,
                shares=shares,
                price_per_share=price,
                value_usd=shares * price,
                filing_url=filing_url,
            )
        )
        new_events += 1

    return new_events


def run(days_back: int = 3) -> None:
    ensure_schema()
    client = SecClient()

    total_checked = 0
    total_new_events = 0

    with SessionLocal() as db:
        for offset in range(days_back):
            day = date.today() - timedelta(days=offset)
            entries = [e for e in client.get_daily_index(day) if e["form"] == "4"]
            print(f"{day}: {len(entries)} Form 4 filing(s)")

            for entry in entries:
                accession_no = entry["filename"].rsplit("/", 1)[-1].removesuffix(".txt")
                total_checked += 1
                try:
                    new_events = _ingest_one_form4(db, client, entry["cik10"], accession_no, day)
                    total_new_events += new_events
                    db.commit()
                except Exception as exc:  # noqa: BLE001 - keep ingesting the rest of the day's filings
                    db.rollback()
                    print(f"  [warn] {entry['name']} ({accession_no}): {exc}", file=sys.stderr)

                if total_checked % 200 == 0:
                    print(f"  checked {total_checked} filing(s), {total_new_events} new director sell(s) so far")

    print(f"Done. Checked {total_checked} Form 4 filing(s), {total_new_events} new director sell(s) ingested.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days-back", type=int, default=3, help="How many recent days to check (default 3)")
    args = parser.parse_args()
    run(days_back=args.days_back)


if __name__ == "__main__":
    main()
