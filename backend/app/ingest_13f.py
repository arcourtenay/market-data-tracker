"""Ingests one fund's latest Form 13F-HR holdings (a quarterly institutional
manager holdings disclosure) from SEC EDGAR.

Funds aren't auto-discovered - each one is added explicitly by CIK. Re-running
for a fund replaces its stored holdings wholesale with whatever its current
latest 13F-HR says; we only track the latest filing, not a history of past
quarters.

Note: this assumes the information table's <value> is in whole dollars, which
is true for filings made under SEC's current (2023+) instructions. An older
fund whose only history predates that (unlikely to be anyone's "latest"
filing today) would need a x1000 adjustment this doesn't do.

Usage:
    python -m app.ingest_13f --cik 0001541448 --name "Veritas Asset Management"
"""

import argparse
from datetime import datetime
from xml.etree import ElementTree as ET

from .database import SessionLocal, ensure_schema
from .models import Fund, FundHolding
from .sec_client import SecClient

_INFO_TABLE_NS = {"n": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}


def _latest_13f_hr(submissions: dict) -> dict | None:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    for idx, form in enumerate(forms):
        if form == "13F-HR":
            return {
                "accession_no": recent["accessionNumber"][idx],
                "filing_date": recent["filingDate"][idx],
                "period_of_report": recent["reportDate"][idx],
            }
    return None


def _find_info_table_filename(index_json: dict) -> str | None:
    for item in index_json.get("directory", {}).get("item", []):
        if "infotable" in item["name"].lower():
            return item["name"]
    return None


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


def run(cik: str, name: str) -> None:
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

        submissions = client.get_submissions(cik10)
        latest = _latest_13f_hr(submissions)
        if latest is None:
            print(f"No 13F-HR filings found for {name} ({cik10})")
            return

        accession_nodash = latest["accession_no"].replace("-", "")
        index_json = client.get_json(
            f"https://www.sec.gov/Archives/edgar/data/{cik_nozero}/{accession_nodash}/index.json"
        )
        info_table_name = _find_info_table_filename(index_json)
        if info_table_name is None:
            print(f"Could not find an information table in {name}'s latest 13F-HR ({latest['accession_no']})")
            return

        xml_text = client.get_text(
            f"https://www.sec.gov/Archives/edgar/data/{cik_nozero}/{accession_nodash}/{info_table_name}"
        )
        holdings = _parse_info_table(xml_text)

        db.query(FundHolding).filter(FundHolding.fund_id == fund.id).delete()
        period_of_report = datetime.strptime(latest["period_of_report"], "%Y-%m-%d").date()
        filing_date = datetime.strptime(latest["filing_date"], "%Y-%m-%d").date()
        for holding in holdings:
            db.add(
                FundHolding(
                    fund_id=fund.id,
                    accession_no=latest["accession_no"],
                    period_of_report=period_of_report,
                    filing_date=filing_date,
                    **holding,
                )
            )
        db.commit()
        print(f"Ingested {len(holdings)} holdings for {name} as of {period_of_report} (filed {filing_date})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cik", required=True, help="The fund's SEC CIK number")
    parser.add_argument("--name", required=True, help="Display name for the fund")
    args = parser.parse_args()
    run(args.cik, args.name)


if __name__ == "__main__":
    main()
