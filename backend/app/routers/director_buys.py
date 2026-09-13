from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Company, DirectorBuyEvent
from ..schemas import DirectorBuyEventOut

router = APIRouter(prefix="/api/director-buys", tags=["director-buys"])


@router.get("", response_model=list[DirectorBuyEventOut])
def list_director_buys(
    search: str | None = Query(None, description="Match against company name, ticker, or director name"),
    filed_from: date | None = Query(None, description="Only filings on/after this date"),
    filed_to: date | None = Query(None, description="Only filings on/before this date"),
    min_value_usd: float | None = Query(None, description="Minimum purchase value in $"),
    limit: int | None = Query(None, description="Omit to return every matching event"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(DirectorBuyEvent).options(joinedload(DirectorBuyEvent.company)).join(Company)

    if search:
        like = f"%{search}%"
        query = query.filter(
            (Company.name.ilike(like))
            | (Company.ticker.ilike(like))
            | (DirectorBuyEvent.reporting_owner_name.ilike(like))
        )
    if filed_from:
        query = query.filter(DirectorBuyEvent.filing_date >= filed_from)
    if filed_to:
        query = query.filter(DirectorBuyEvent.filing_date <= filed_to)
    if min_value_usd is not None:
        query = query.filter(DirectorBuyEvent.value_usd >= min_value_usd)

    query = query.order_by(DirectorBuyEvent.filing_date.desc()).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()
