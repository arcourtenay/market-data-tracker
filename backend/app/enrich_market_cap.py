"""Fills in Company.market_cap_usd = live Yahoo Finance price x SEC-reported
shares outstanding (dei:EntityCommonStockSharesOutstanding, from the most
recent 10-Q/10-K cover page), and Company.ipo_proceeds_usd for companies
with an IPO or SPAC-IPO event.

EDGAR has no live market cap field, and Yahoo's own market-cap/shares fields
now require an auth crumb we don't have - so this combines the two: a live
price alone means nothing without a share count, and a share count alone
doesn't move with the market. Together they approximate live market cap.

Three phases each run:
  1. Shares outstanding rarely changes, so it's only looked up once per
     company (gated by shares_outstanding_checked_at) via SEC XBRL.
  2. Price is refetched from Yahoo for every company with a ticker on every
     run, so re-running this periodically keeps market_cap_usd close to live.
  3. IPO proceeds (a fixed historical fact, from SEC XBRL
     us-gaap:ProceedsFromIssuanceInitialPublicOffering / ProceedsFromIssuanceOfCommonStock)
     is usually not available until the company's first post-IPO 10-Q/10-K,
     so this keeps retrying every run for companies still missing it.

Usage:
    python -m app.enrich_market_cap
    python -m app.enrich_market_cap --limit 50
"""

import argparse
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func

from .database import SessionLocal, ensure_schema
from .models import Company, IpoEvent, SpacEvent
from .sec_client import SecClient
from .yahoo_client import YahooClient

_IPO_PROCEEDS_TAGS = ("ProceedsFromIssuanceInitialPublicOffering", "ProceedsFromIssuanceOfCommonStock")

# Some multi-class-share filers (e.g. Berkshire Hathaway) stopped reporting a
# plain, non-dimensional EntityCommonStockSharesOutstanding years ago once they
# started breaking share classes out with XBRL dimensions - which this simple
# companyconcept lookup can't reconstruct. Rather than silently computing a
# market cap off an 8-year-stale share count, treat anything this old as
# "unknown" so the company is excluded from the filter instead of misrepresented.
_MAX_SHARES_AGE_DAYS = 400


def _latest_shares_outstanding(concept_json: dict) -> tuple[float, str] | None:
    """Multi-class-share companies (e.g. BRK-A/BRK-B) report one entry per class
    for the same date - summing all entries as-of the latest date approximates
    total shares outstanding across classes, rather than arbitrarily picking one
    class and grossly undercounting."""
    entries = concept_json.get("units", {}).get("shares", [])
    if not entries:
        return None
    latest_end = max(e.get("end", "") for e in entries)
    if date.today() - date.fromisoformat(latest_end) > timedelta(days=_MAX_SHARES_AGE_DAYS):
        return None
    total = sum(e["val"] for e in entries if e.get("end") == latest_end)
    return total, latest_end


def _fill_shares_outstanding(db, sec_client: SecClient, limit: int | None) -> None:
    query = db.query(Company).filter(Company.shares_outstanding_checked_at.is_(None))
    if limit:
        query = query.limit(limit)
    companies = query.all()

    total = len(companies)
    print(f"shares outstanding: {total} compan(ies) to check")

    for idx, company in enumerate(companies, start=1):
        try:
            concept = sec_client.get_company_concept(company.cik, "dei", "EntityCommonStockSharesOutstanding")
            result = _latest_shares_outstanding(concept) if concept else None
            if result:
                value, as_of = result
                company.shares_outstanding = value
                company.shares_outstanding_as_of = datetime.strptime(as_of, "%Y-%m-%d").date()
            else:
                # Unknown (or no longer trustworthy) share count - don't leave a
                # market cap computed from a stale/prior value lying around.
                company.shares_outstanding = None
                company.shares_outstanding_as_of = None
                company.market_cap_usd = None
                company.market_cap_updated_at = None
            company.shares_outstanding_checked_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - keep going, leave this row for the next run
            db.rollback()
            print(f"  [warn] {company.ticker or company.cik}: {exc}", file=sys.stderr)

        if idx % 50 == 0 or idx == total:
            print(f"  processed {idx}/{total}")


def _refresh_prices(db, yahoo_client: YahooClient, limit: int | None) -> None:
    query = db.query(Company).filter(Company.ticker.isnot(None), Company.shares_outstanding.isnot(None))
    if limit:
        query = query.limit(limit)
    companies = query.all()

    total = len(companies)
    print(f"prices: {total} compan(ies) to refresh")

    for idx, company in enumerate(companies, start=1):
        try:
            price = yahoo_client.get_price(company.ticker)
            if price:
                company.market_cap_usd = price * company.shares_outstanding
                company.market_cap_updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as exc:  # noqa: BLE001 - keep going, leave this row for the next run
            db.rollback()
            print(f"  [warn] {company.ticker or company.cik}: {exc}", file=sys.stderr)

        if idx % 50 == 0 or idx == total:
            print(f"  processed {idx}/{total}")


def _matching_ipo_proceeds(concept_json: dict, event_date: date) -> float | None:
    """Picks the reported amount for the duration period containing the IPO
    filing date, preferring the shortest (most precise) matching period -
    XBRL repeats the same total as a comparative figure in later quarters'
    filings, so this avoids just grabbing whichever one happens to load."""
    best: tuple[int, float] | None = None
    for entry in concept_json.get("units", {}).get("USD", []):
        val = entry.get("val")
        start, end = entry.get("start"), entry.get("end")
        if not val or not start or not end:
            continue
        try:
            period_start, period_end = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError:
            continue
        if period_start <= event_date <= period_end:
            duration = (period_end - period_start).days
            if best is None or duration < best[0]:
                best = (duration, val)
    return best[1] if best else None


def _fill_ipo_proceeds(db, sec_client: SecClient, limit: int | None) -> None:
    """Only checks companies with a known IPO/SPAC-IPO event and still-missing
    proceeds - most companies never file this concept at all, so checking
    everyone would be almost all wasted requests."""
    event_dates: dict[int, date] = {}
    for company_id, filing_date in db.query(SpacEvent.company_id, func.min(SpacEvent.filing_date)).filter(
        SpacEvent.stage == "ipo"
    ).group_by(SpacEvent.company_id):
        event_dates[company_id] = filing_date
    for company_id, filing_date in db.query(IpoEvent.company_id, func.min(IpoEvent.filing_date)).filter(
        IpoEvent.stage == "priced"
    ).group_by(IpoEvent.company_id):
        event_dates.setdefault(company_id, filing_date)

    if not event_dates:
        return

    query = db.query(Company).filter(Company.id.in_(event_dates.keys()), Company.ipo_proceeds_usd.is_(None))
    if limit:
        query = query.limit(limit)
    companies = query.all()

    total = len(companies)
    print(f"ipo proceeds: {total} compan(ies) to check")

    for idx, company in enumerate(companies, start=1):
        try:
            event_date = event_dates[company.id]
            for tag in _IPO_PROCEEDS_TAGS:
                concept = sec_client.get_company_concept(company.cik, "us-gaap", tag)
                value = _matching_ipo_proceeds(concept, event_date) if concept else None
                if value:
                    company.ipo_proceeds_usd = value
                    db.commit()
                    break
        except Exception as exc:  # noqa: BLE001 - keep going, leave this row for the next run
            db.rollback()
            print(f"  [warn] {company.ticker or company.cik}: {exc}", file=sys.stderr)

        if idx % 50 == 0 or idx == total:
            print(f"  processed {idx}/{total}")


def run(limit: int | None = None) -> None:
    ensure_schema()
    with SessionLocal() as db:
        _fill_shares_outstanding(db, SecClient(), limit)
        _refresh_prices(db, YahooClient(), limit)
        _fill_ipo_proceeds(db, SecClient(), limit)
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Cap on companies processed per phase (testing)")
    args = parser.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
