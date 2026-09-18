"""Ingests activist share buying/selling from SEC Schedule 13D and 13D/A
filings.

Unlike Form 4 (which reports a discrete transaction: N shares at $X, coded
P/S), Schedule 13D's structured cover page reports an activist's TOTAL
current beneficial ownership and % of class at filing time - a snapshot, not
a transaction. So buying/selling is detected by diffing consecutive filings
for the same (company, reporting person) pair:

  - A brand-new Schedule 13D (no prior snapshot for that pair) is itself a
    "buy" of the whole position (a fresh >5% activist stake).
  - A Schedule 13D/A showing MORE shares than that activist's last known
    position is a "buy" of the increase.
  - A Schedule 13D/A showing FEWER shares is a "sell" of the decrease.
  - No change in shares produces no buy/sell event (the snapshot is still
    recorded, so it remains the baseline for the next filing's diff).
  - A Schedule 13D/A with NO prior snapshot for that pair (the position was
    established before our lookback window) produces no buy/sell event either
    - the true baseline is unknown, so treating the full current stake as a
    "buy" would wildly overstate it (e.g. a decades-old founder/family holding
    surfacing as a fresh multi-billion-dollar purchase). The snapshot is still
    recorded as the baseline for the next filing.

13D has no per-share transaction price like Form 4 does, so price_per_share/
value_usd are a best-effort estimate: a share price looked up near the
filing's event date via Yahoo Finance. Left null when that lookup fails -
never fabricated.

A 13D filing can list several affiliated reporting persons as one group
(e.g. a fund, its GP, and an individual), all with identical holdings - only
the first-listed person is used, to avoid a near-duplicate row per affiliate
for what is really one activist campaign.

Like ingest_director_buys.py, this is a pure rolling feed off SEC's daily
index - the filer's full history isn't scanned, only what appears in the
requested day window (so a first run should use a wide --days-back to build
up enough prior snapshots for accurate diffing).

Usage:
    python -m app.ingest_activist_trades                  # last 3 days
    python -m app.ingest_activist_trades --days-back 14    # last 14 days
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .database import SessionLocal, ensure_schema
from .ingest import _upsert_company
from .models import ActivistBuyEvent, ActivistPosition, ActivistSellEvent
from .sec_client import SecClient
from .yahoo_client import YahooClient

CANDIDATE_FORMS = ("SCHEDULE 13D", "SCHEDULE 13D/A")
_NS = {"n": "http://www.sec.gov/edgar/schedule13D"}


def _text(el: ET.Element | None, path: str) -> str | None:
    found = el.find(path, _NS) if el is not None else None
    return found.text.strip() if found is not None and found.text else None


def _find_13d_xml(client: SecClient, cik_no_zeros: str, accession_nodash: str) -> ET.Element | None:
    """The structured cover-page XML is conventionally primary_doc.xml, but -
    as with Form 4 and 13F - try every .xml file in the filing until one
    actually parses as a Schedule 13D submission, rather than assuming the
    name. Older/non-adopting filers may have no structured XML at all, in
    which case this returns None and the filing is skipped."""
    index = client.get_json(f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_nodash}/index.json")
    xml_names = [item["name"] for item in index.get("directory", {}).get("item", []) if item["name"].endswith(".xml")]
    for name in xml_names:
        text = client.get_text(f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_nodash}/{name}")
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            continue
        if root.tag.endswith("}edgarSubmission") and root.find("n:formData/n:coverPageHeader", _NS) is not None:
            return root
    return None


def _build_ticker_map(client: SecClient) -> dict[str, str]:
    tickers_data = client.get_company_tickers()
    return {str(entry["cik_str"]).zfill(10): entry["ticker"] for entry in tickers_data.values() if entry.get("ticker")}


def _ingest_one_filing(
    db: Session,
    client: SecClient,
    yahoo: YahooClient,
    filer_cik10: str,
    form: str,
    accession_no: str,
    filing_date: date,
    ticker_map: dict[str, str],
) -> int:
    cik_no_zeros = str(int(filer_cik10))
    accession_nodash = accession_no.replace("-", "")
    root = _find_13d_xml(client, cik_no_zeros, accession_nodash)
    if root is None:
        return 0

    cover = root.find("n:formData/n:coverPageHeader", _NS)
    issuer = cover.find("n:issuerInfo", _NS) if cover is not None else None
    issuer_cik = _text(issuer, "n:issuerCIK")
    issuer_name = _text(issuer, "n:issuerName")
    if not issuer_cik or not issuer_name:
        return 0
    issuer_cik10 = issuer_cik.zfill(10)

    reporting_persons = root.findall("n:formData/n:reportingPersons/n:reportingPersonInfo", _NS)
    if not reporting_persons:
        return 0
    person = reporting_persons[0]
    person_cik = _text(person, "n:reportingPersonCIK")
    person_name = _text(person, "n:reportingPersonName") or "Unknown"
    person_key = person_cik.zfill(10) if person_cik else person_name.strip().lower()

    shares_str = _text(person, "n:aggregateAmountOwned")
    if not shares_str:
        return 0
    try:
        shares_owned = float(shares_str.replace(",", ""))
    except ValueError:
        return 0
    percent_str = _text(person, "n:percentOfClass")
    percent_of_class = float(percent_str) if percent_str else None

    event_date_str = _text(cover, "n:dateOfEvent")
    try:
        event_date = datetime.strptime(event_date_str, "%m/%d/%Y").date() if event_date_str else filing_date
    except ValueError:
        event_date = filing_date

    filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_nodash}/{accession_no}-index.htm"

    # The prior snapshot for this (company, reporting person) pair - if any -
    # is the baseline this filing's holdings are diffed against.
    company = _upsert_company(db, issuer_cik10, issuer_name, ticker_map.get(issuer_cik10), None, None)
    prior = (
        db.query(ActivistPosition)
        .filter(ActivistPosition.company_id == company.id, ActivistPosition.reporting_person_key == person_key)
        .order_by(ActivistPosition.event_date.desc(), ActivistPosition.filing_date.desc())
        .first()
    )

    db.add(
        ActivistPosition(
            company_id=company.id,
            accession_no=accession_no,
            form_type=form,
            reporting_person_key=person_key,
            reporting_person_name=person_name,
            shares_owned=shares_owned,
            percent_of_class=percent_of_class,
            event_date=event_date,
            filing_date=filing_date,
            filing_url=filing_url,
        )
    )

    if prior is None and form == "SCHEDULE 13D/A":
        # An amendment with no prior snapshot means the position predates our
        # lookback window - the true baseline is unknown, so there's nothing
        # honest to diff against. Bank the snapshot and wait for the next
        # filing for this pair.
        return 0

    delta = shares_owned - prior.shares_owned if prior else shares_owned
    if delta == 0:
        return 0

    ticker = ticker_map.get(issuer_cik10)
    price = yahoo.get_price_on_date(ticker, event_date) if ticker else None
    value_usd = abs(delta) * price if price else None

    if delta > 0:
        db.add(
            ActivistBuyEvent(
                company_id=company.id,
                accession_no=accession_no,
                reporting_person_name=person_name,
                is_new_position=prior is None,
                shares=delta,
                price_per_share=price,
                value_usd=value_usd,
                event_date=event_date,
                filing_date=filing_date,
                filing_url=filing_url,
            )
        )
    else:
        db.add(
            ActivistSellEvent(
                company_id=company.id,
                accession_no=accession_no,
                reporting_person_name=person_name,
                shares=abs(delta),
                price_per_share=price,
                value_usd=value_usd,
                event_date=event_date,
                filing_date=filing_date,
                filing_url=filing_url,
            )
        )
    return 1


def run(days_back: int = 3) -> None:
    ensure_schema()
    client = SecClient()
    yahoo = YahooClient()
    ticker_map = _build_ticker_map(client)

    total_checked = 0
    total_new_events = 0

    with SessionLocal() as db:
        for offset in range(days_back, -1, -1):
            day = date.today() - timedelta(days=offset)
            entries = [e for e in client.get_daily_index(day) if e["form"] in CANDIDATE_FORMS]
            print(f"{day}: {len(entries)} Schedule 13D/13D-A filing(s)")

            for entry in entries:
                accession_no = entry["filename"].rsplit("/", 1)[-1].removesuffix(".txt")
                total_checked += 1
                try:
                    exists = (
                        db.query(ActivistPosition).filter(ActivistPosition.accession_no == accession_no).one_or_none()
                    )
                    if exists:
                        continue
                    new_events = _ingest_one_filing(
                        db, client, yahoo, entry["cik10"], entry["form"], accession_no, day, ticker_map
                    )
                    total_new_events += new_events
                    db.commit()
                except Exception as exc:  # noqa: BLE001 - keep ingesting the rest of the day's filings
                    db.rollback()
                    print(f"  [warn] {entry['name']} ({accession_no}): {exc}", file=sys.stderr)

                if total_checked % 100 == 0:
                    print(f"  checked {total_checked} filing(s), {total_new_events} new buy/sell event(s) so far")

    print(f"Done. Checked {total_checked} filing(s), {total_new_events} new activist buy/sell event(s) ingested.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days-back", type=int, default=3, help="How many recent days to check (default 3)")
    args = parser.parse_args()
    run(days_back=args.days_back)


if __name__ == "__main__":
    main()
