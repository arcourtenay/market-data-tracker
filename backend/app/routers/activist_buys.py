from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import ActivistBuyEvent, Company
from ..schemas import ActivistBuyEventOut

router = APIRouter(prefix="/api/activist-buys", tags=["activist-buys"])


@router.get("", response_model=list[ActivistBuyEventOut])
def list_activist_buys(
    search: str | None = Query(None, description="Match against company name, ticker, or activist name"),
    filed_from: date | None = Query(None, description="Only filings on/after this date"),
    filed_to: date | None = Query(None, description="Only filings on/before this date"),
    min_value_usd: float | None = Query(None, description="Minimum estimated purchase value in $"),
    limit: int | None = Query(None, description="Omit to return every matching event"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(ActivistBuyEvent).options(joinedload(ActivistBuyEvent.company)).join(Company)

    if search:
        like = f"%{search}%"
        query = query.filter(
            (Company.name.ilike(like))
            | (Company.ticker.ilike(like))
            | (ActivistBuyEvent.reporting_person_name.ilike(like))
        )
    if filed_from:
        query = query.filter(ActivistBuyEvent.filing_date >= filed_from)
    if filed_to:
        query = query.filter(ActivistBuyEvent.filing_date <= filed_to)
    if min_value_usd is not None:
        query = query.filter(ActivistBuyEvent.value_usd >= min_value_usd)

    query = query.order_by(ActivistBuyEvent.filing_date.desc()).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()
