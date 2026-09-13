"""Ingests a fund's N most recent Form 13F-HR quarterly holdings disclosures
from SEC EDGAR (default: last 4 quarters).

Funds aren't auto-discovered - each one is added explicitly by CIK. Re-running
is idempotent per quarter: each quarter's holdings are replaced wholesale by
whatever that quarter's 13F-HR currently says, but other quarters already
stored are left alone. Quarters older than the N most recently ingested are
NOT automatically pruned - re-run with the same --quarters value periodically
to keep only a rolling window, if desired.

Note: this assumes each information table's <value> is in whole dollars, which
is true for filings made under SEC's current (2023+) instructions. Quarters
older than that boundary would need a x1000 adjustment this doesn't do.

Usage:
    python -m app.ingest_13f --cik 0001541448 --name "Veritas Asset Management"
    python -m app.ingest_13f --cik 0001541448 --name "Veritas Asset Management" --quarters 8
"""

import argparse
from datetime import datetime
from xml.etree import ElementTree as ET

from .database import SessionLocal, ensure_schema
from .models import Fund, FundHolding
from .sec_client import SecClient

_INFO_TABLE_NS = {"n": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}


def _recent_13f_hr_filings(submissions: dict, count: int) -> list[dict]:
    """Returns up to `count` of the most recent 13F-HR filings, newest first.
    Excludes 13F-HR/A amendments (exact form match), so each result is a
    distinct quarter, not a duplicate/amended view of one already returned."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filings = []
    for idx, form in enumerate(forms):
        if form == "13F-HR":
            filings.append(
                {
                    "accession_no": recent["accessionNumber"][idx],
                    "filing_date": recent["filingDate"][idx],
                    "period_of_report": recent["reportDate"][idx],
                }
            )
        if len(filings) >= count:
            break
    return filings


def _find_info_table_filename(index_json: dict) -> str | None:
    """The information table's filename varies by filer/filing agent
    (infotable.xml, Form13F2q2026TABLE.xml, etc.) - the only name that's
    actually standardized across all 13F-HR filers is primary_doc.xml (the
    cover page). So: take every .xml file that isn't primary_doc.xml: if there
    are several (rare), the information table is the largest one - it lists
    every holding, so it dwarfs any other exhibit."""
    candidates = [
        item
        for item in index_json.get("directory", {}).get("item", [])
        if item["name"].lower().endswith(".xml") and item["name"].lower() != "primary_doc.xml"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: int(item.get("size") or 0))["name"]


def _parse_info_table(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    holdings = []
    for info in root.findall("n:infoTable", _INFO_TABLE_NS):

        def field(tag: str, parent=info) -> str | None:
            el = parent.find(f"n:{tag}", _INFO_TABLE_NS)
            return el.text if el is not None else None

        shrs_el = info.find("n:shrsOrPrnAmt", _INFO_TABLE_NS)
        holdings.append(
            {
                "issuer_name": field("nameOfIssuer"),
                "cusip": field("cusip"),
                "value_usd": float(field("value") or 0),
                "shares": float(field("sshPrnamt", shrs_el) or 0) if shrs_el is not None else 0.0,
                "share_class": field("sshPrnamtType", shrs_el) if shrs_el is not None else None,
            }
        )
    return holdings


def _ingest_one_filing(db, client: SecClient, cik_nozero: str, fund_id: int, filing: dict) -> int:
    accession_nodash = filing["accession_no"].replace("-", "")
    index_json = client.get_json(
        f"https://www.sec.gov/Archives/edgar/data/{cik_nozero}/{accession_nodash}/index.json"
    )
    info_table_name = _find_info_table_filename(index_json)
    if info_table_name is None:
        print(f"  [warn] no information table found in {filing['accession_no']} - skipping this quarter")
        return None

    xml_text = client.get_text(
        f"https://www.sec.gov/Archives/edgar/data/{cik_nozero}/{accession_nodash}/{info_table_name}"
    )
    holdings = _parse_info_table(xml_text)

    period_of_report = datetime.strptime(filing["period_of_report"], "%Y-%m-%d").date()
    filing_date = datetime.strptime(filing["filing_date"], "%Y-%m-%d").date()

    # Replace this specific quarter only - other quarters already stored are untouched.
    db.query(FundHolding).filter(
        FundHolding.fund_id == fund_id, FundHolding.period_of_report == period_of_report
    ).delete()
    for holding in holdings:
        db.add(
            FundHolding(
                fund_id=fund_id,
                accession_no=filing["accession_no"],
                period_of_report=period_of_report,
                filing_date=filing_date,
                **holding,
            )
        )
    db.commit()
    return len(holdings)


def run(cik: str, name: str, quarters: int = 4) -> None:
    ensure_schema()
    cik10 = cik.zfill(10)
    cik_nozero = str(int(cik10))
    client = SecClient()

    with SessionLocal() as db:
        fund = db.query(Fund).filter(Fund.cik == cik10).one_or_none()
        if fund is None:
            fund = Fund(cik=cik10, name=name)
            db.add(fund)
        else:
            fund.name = name
        db.flush()
        fund_id = fund.id
        db.commit()

        submissions = client.get_submissions(cik10)
        filings = _recent_13f_hr_filings(submissions, quarters)
        if not filings:
            print(f"No 13F-HR filings found for {name} ({cik10})")
            return

        for filing in filings:
            count = _ingest_one_filing(db, client, cik_nozero, fund_id, filing)
            if count is not None:
                print(f"  {filing['period_of_report']}: {count} holdings (filed {filing['filing_date']})")

    print(f"Done. Ingested {len(filings)} quarter(s) for {name}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cik", required=True, help="The fund's SEC CIK number")
    parser.add_argument("--name", required=True, help="Display name for the fund")
    parser.add_argument("--quarters", type=int, default=4, help="How many recent quarters to ingest (default 4)")
    args = parser.parse_args()
    run(args.cik, args.name, quarters=args.quarters)


if __name__ == "__main__":
    main()
