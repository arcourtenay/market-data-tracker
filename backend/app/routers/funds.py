from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Fund, FundHolding
from ..schemas import FundHoldingsOut, FundOut

router = APIRouter(prefix="/api/funds", tags=["funds"])


@router.get("", response_model=list[FundOut])
def list_funds(db: Session = Depends(get_db)):
    return db.query(Fund).order_by(func.lower(Fund.name)).all()


@router.get("/{fund_id}/quarters", response_model=list[date])
def list_fund_quarters(fund_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(FundHolding.period_of_report)
        .filter(FundHolding.fund_id == fund_id)
        .distinct()
        .order_by(FundHolding.period_of_report.desc())
        .all()
    )
    return [row[0] for row in rows]


@router.get("/{fund_id}/holdings", response_model=FundHoldingsOut)
def get_fund_holdings(
    fund_id: int,
    period: date | None = Query(None, description="A period_of_report date; omit for the latest quarter"),
    db: Session = Depends(get_db),
):
    fund = db.query(Fund).filter(Fund.id == fund_id).one_or_none()
    if fund is None:
        raise HTTPException(status_code=404, detail="Fund not found")

    target_period = period
    if target_period is None:
        target_period = (
            db.query(func.max(FundHolding.period_of_report)).filter(FundHolding.fund_id == fund_id).scalar()
        )
    if target_period is None:
        raise HTTPException(status_code=404, detail="No 13F holdings ingested yet for this fund")

    all_holdings = (
        db.query(FundHolding)
        .filter(FundHolding.fund_id == fund_id, FundHolding.period_of_report == target_period)
        .all()
    )
    if not all_holdings:
        raise HTTPException(status_code=404, detail="No 13F holdings ingested yet for this fund/quarter")

    # Some filers submit a placeholder line (issuer "NA", $0, 0 shares) when they have
    # zero 13(f) securities to report that quarter rather than an empty table - drop
    # it, it's not a real holding.
    holdings = [h for h in all_holdings if h.value_usd > 0]
    filing_date_source = holdings[0] if holdings else all_holdings[0]

    total_value_usd = sum(h.value_usd for h in holdings)

    # Quarter-over-quarter share count change: find the quarter immediately
    # before this one (for this fund) and compare shares by issuer.
    all_periods = [
        row[0]
        for row in db.query(FundHolding.period_of_report)
        .filter(FundHolding.fund_id == fund_id)
        .distinct()
        .order_by(FundHolding.period_of_report.desc())
        .all()
    ]
    prior_shares_by_issuer: dict[str, float] = defaultdict(float)
    try:
        idx = all_periods.index(target_period)
        prior_period = all_periods[idx + 1] if idx + 1 < len(all_periods) else None
    except ValueError:
        prior_period = None
    if prior_period is not None:
        prior_rows = (
            db.query(FundHolding.issuer_name, FundHolding.shares)
            .filter(FundHolding.fund_id == fund_id, FundHolding.period_of_report == prior_period)
            .all()
        )
        for issuer_name, shares in prior_rows:
            prior_shares_by_issuer[issuer_name] += shares

    # A fund can report the same issuer as several lines - different CUSIPs for
    # different share classes, or split across sub-accounts/managers - so group
    # by issuer name into one row each, summing value and shares across every
    # line for that issuer (including all its share classes).
    grouped: dict[str, list[FundHolding]] = defaultdict(list)
    for h in holdings:
        grouped[h.issuer_name].append(h)

    def share_change_pct(issuer_name: str, shares: float) -> float | None:
        prior_shares = prior_shares_by_issuer.get(issuer_name)
        if not prior_shares:
            return None
        return (shares - prior_shares) / prior_shares * 100

    aggregated = []
    for issuer_name, rows in grouped.items():
        agg_value = sum(r.value_usd for r in rows)
        agg_shares = sum(r.shares for r in rows)
        aggregated.append(
            {
                "issuer_name": issuer_name,
                "cusip": rows[0].cusip,
                "value_usd": agg_value,
                "shares": agg_shares,
                "share_class": rows[0].share_class if len(rows) == 1 else None,
                "weight_pct": (agg_value / total_value_usd * 100) if total_value_usd else 0.0,
                "share_change_pct": share_change_pct(issuer_name, agg_shares),
            }
        )
    aggregated.sort(key=lambda h: h["value_usd"], reverse=True)

    return {
        "fund": fund,
        "period_of_report": filing_date_source.period_of_report,
        "prior_period_of_report": prior_period,
        "filing_date": filing_date_source.filing_date,
        "total_value_usd": total_value_usd,
        "holdings": aggregated,
    }
