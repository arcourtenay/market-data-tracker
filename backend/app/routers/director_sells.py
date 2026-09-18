from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Company, DirectorSellEvent
from ..schemas import DirectorSellEventOut

router = APIRouter(prefix="/api/director-sells", tags=["director-sells"])


@router.get("", response_model=list[DirectorSellEventOut])
def list_director_sells(
    search: str | None = Query(None, description="Match against company name, ticker, or director name"),
    filed_from: date | None = Query(None, description="Only filings on/after this date"),
    filed_to: date | None = Query(None, description="Only filings on/before this date"),
    min_value_usd: float | None = Query(None, description="Minimum sale value in $"),
    limit: int | None = Query(None, description="Omit to return every matching event"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(DirectorSellEvent).options(joinedload(DirectorSellEvent.company)).join(Company)

    if search:
        like = f"%{search}%"
        query = query.filter(
            (Company.name.ilike(like))
            | (Company.ticker.ilike(like))
            | (DirectorSellEvent.reporting_owner_name.ilike(like))
        )
    if filed_from:
        query = query.filter(DirectorSellEvent.filing_date >= filed_from)
    if filed_to:
        query = query.filter(DirectorSellEvent.filing_date <= filed_to)
    if min_value_usd is not None:
        query = query.filter(DirectorSellEvent.value_usd >= min_value_usd)

    query = query.order_by(DirectorSellEvent.filing_date.desc()).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()
