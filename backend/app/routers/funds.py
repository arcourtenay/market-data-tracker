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
    return db.query(Fund).order_by(Fund.name).all()


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

    holdings = (
        db.query(FundHolding)
        .filter(FundHolding.fund_id == fund_id, FundHolding.period_of_report == target_period)
        .order_by(FundHolding.value_usd.desc())
        .all()
    )
    if not holdings:
        raise HTTPException(status_code=404, detail="No 13F holdings ingested yet for this fund/quarter")

    total_value_usd = sum(h.value_usd for h in holdings)

    return {
        "fund": fund,
        "period_of_report": holdings[0].period_of_report,
        "filing_date": holdings[0].filing_date,
        "total_value_usd": total_value_usd,
        "holdings": [
            {
                "issuer_name": h.issuer_name,
                "cusip": h.cusip,
                "value_usd": h.value_usd,
                "shares": h.shares,
                "share_class": h.share_class,
                "weight_pct": (h.value_usd / total_value_usd * 100) if total_value_usd else 0.0,
            }
            for h in holdings
        ],
    }
