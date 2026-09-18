"""Ingests a fund's N most recent Form 13F-HR quarterly holdings disclosures
from SEC EDGAR (default: last 4 quarters).

Funds aren't auto-discovered - each one is added explicitly by CIK (or, for a
multi-entity fund family like Founders Fund, a list of CIKs - one per fund
vintage - that should be shown as a single combined entry; see Fund's
docstring in models.py). Re-running is idempotent per quarter: each quarter's
holdings are replaced wholesale by whatever that quarter's 13F-HR currently
says, but other quarters already stored are left alone. Quarters older than
the N most recently ingested are NOT automatically pruned - re-run with the
same --quarters value periodically to keep only a rolling window, if desired.

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
from .models import Fund, FundCik, FundHolding
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


def _ingest_one_filing(db, client: SecClient, cik_nozero: str, cik10: str, fund_id: int, filing: dict) -> int:
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

    # Replace this CIK's holdings for this quarter only - other quarters, and any
    # other CIK's holdings for the SAME quarter (multi-entity funds), are untouched.
    # Also sweeps up any pre-multi-CIK rows (source_cik still NULL) for this fund
    # and quarter, so a single-CIK fund transitions cleanly the next time it's
    # re-ingested rather than accumulating an orphaned duplicate set.
    db.query(FundHolding).filter(
        FundHolding.fund_id == fund_id,
        FundHolding.period_of_report == period_of_report,
        (FundHolding.source_cik == cik10) | (FundHolding.source_cik.is_(None)),
    ).delete(synchronize_session=False)
    for holding in holdings:
        db.add(
            FundHolding(
                fund_id=fund_id,
                source_cik=cik10,
                accession_no=filing["accession_no"],
                period_of_report=period_of_report,
                filing_date=filing_date,
                **holding,
            )
        )
    db.commit()
    return len(holdings)


def _find_fund_by_any_cik(db, cik10: str) -> Fund | None:
    fund = db.query(Fund).filter(Fund.cik == cik10).one_or_none()
    if fund:
        return fund
    fund_cik = db.query(FundCik).filter(FundCik.cik == cik10).one_or_none()
    return fund_cik.fund if fund_cik else None


def run(cik: str | list[str], name: str, quarters: int = 4) -> None:
    """cik: a single CIK for an ordinary fund, or a list of CIKs for a
    multi-entity fund family (e.g. Founders Fund) that should show as one
    combined entry - holdings from every CIK in the list are ingested into
    the same Fund row and folded together for display by the same
    issuer-name aggregation the API already uses to combine a single filer's
    multiple share classes.

    For a single CIK, `name` is overridden with SEC's own registered name for
    that CIK (the technically-correct name of the actual filer) - unchanged
    from this function's original single-CIK behavior. For a list, there's no
    one "correct" legal name spanning every underlying entity, so `name` is
    used exactly as given (e.g. "Founders Fund")."""
    ensure_schema()
    cik10_list = [c.zfill(10) for c in ([cik] if isinstance(cik, str) else cik)]
    primary_cik10 = cik10_list[0]
    client = SecClient()

    with SessionLocal() as db:
        display_name = name
        if len(cik10_list) == 1:
            # Use SEC's own registered name for this CIK, not whatever we were told
            # to call it - that's the technically-correct name of the actual filer.
            display_name = client.get_submissions(primary_cik10).get("name") or name

        fund = _find_fund_by_any_cik(db, primary_cik10)
        if fund is None:
            fund = Fund(cik=primary_cik10, name=display_name)
            db.add(fund)
        else:
            fund.name = display_name
        db.flush()
        fund_id = fund.id

        existing_extra_ciks = {fc.cik for fc in fund.additional_ciks}
        for extra_cik10 in cik10_list[1:]:
            if extra_cik10 != fund.cik and extra_cik10 not in existing_extra_ciks:
                db.add(FundCik(fund_id=fund_id, cik=extra_cik10))
        db.commit()

        total_quarters = 0
        for cik10 in cik10_list:
            cik_nozero = str(int(cik10))
            submissions = client.get_submissions(cik10)
            filings = _recent_13f_hr_filings(submissions, quarters)
            if not filings:
                print(f"  [warn] no 13F-HR filings found for CIK {cik10}")
                continue
            for filing in filings:
                count = _ingest_one_filing(db, client, cik_nozero, cik10, fund_id, filing)
                if count is not None:
                    prefix = f"[{cik10}] " if len(cik10_list) > 1 else ""
                    print(f"  {prefix}{filing['period_of_report']}: {count} holdings (filed {filing['filing_date']})")
            total_quarters += len(filings)

    if total_quarters == 0:
        print(f"No 13F-HR filings found for {display_name} ({', '.join(cik10_list)})")
        return

    print(f"Done. Ingested {total_quarters} quarter-filing(s) across {len(cik10_list)} CIK(s) for {display_name}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cik", required=True, action="append", help="The fund's SEC CIK number (repeatable)")
    parser.add_argument("--name", required=True, help="Display name for the fund")
    parser.add_argument("--quarters", type=int, default=4, help="How many recent quarters to ingest (default 4)")
    args = parser.parse_args()
    run(args.cik if len(args.cik) > 1 else args.cik[0], args.name, quarters=args.quarters)


if __name__ == "__main__":
    main()
