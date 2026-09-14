from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Company, FinancialResultEvent
from ..schemas import FinancialResultEventOut

router = APIRouter(prefix="/api/financial-results", tags=["financial-results"])


@router.get("", response_model=list[FinancialResultEventOut])
def list_financial_results(
    search: str | None = Query(None, description="Match against company name or ticker"),
    filed_from: date | None = Query(None, description="Only filings on/after this date"),
    filed_to: date | None = Query(None, description="Only filings on/before this date"),
    min_market_cap_millions: float | None = Query(
        None, description="Minimum market cap in $M; companies with no known market cap are excluded"
    ),
    limit: int | None = Query(None, description="Omit to return every matching event"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(FinancialResultEvent).options(joinedload(FinancialResultEvent.company)).join(Company)

    if search:
        like = f"%{search}%"
        query = query.filter((Company.name.ilike(like)) | (Company.ticker.ilike(like)))
    if filed_from:
        query = query.filter(FinancialResultEvent.filing_date >= filed_from)
    if filed_to:
        query = query.filter(FinancialResultEvent.filing_date <= filed_to)
    if min_market_cap_millions is not None:
        query = query.filter(Company.market_cap_usd >= min_market_cap_millions * 1_000_000)

    query = query.order_by(FinancialResultEvent.filing_date.desc()).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()
