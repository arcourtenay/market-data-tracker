"""Fills in Company.market_cap_usd = live Yahoo Finance price x SEC-reported
shares outstanding (dei:EntityCommonStockSharesOutstanding, from the most
recent 10-Q/10-K cover page).

EDGAR has no live market cap field, and Yahoo's own market-cap/shares fields
now require an auth crumb we don't have - so this combines the two: a live
price alone means nothing without a share count, and a share count alone
doesn't move with the market. Together they approximate live market cap.

Two phases each run:
  1. Shares outstanding rarely changes, so it's only looked up once per
     company (gated by shares_outstanding_checked_at) via SEC XBRL.
  2. Price is refetched from Yahoo for every company with a ticker on every
     run, so re-running this periodically keeps market_cap_usd close to live.

Usage:
    python -m app.enrich_market_cap
    python -m app.enrich_market_cap --limit 50
"""

import argparse
import sys
from datetime import date, datetime, timedelta, timezone

from .database import SessionLocal, ensure_schema
from .models import Company
from .sec_client import SecClient
from .yahoo_client import YahooClient

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


def run(limit: int | None = None) -> None:
    ensure_schema()
    with SessionLocal() as db:
        _fill_shares_outstanding(db, SecClient(), limit)
        _refresh_prices(db, YahooClient(), limit)
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Cap on companies processed per phase (testing)")
    args = parser.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
