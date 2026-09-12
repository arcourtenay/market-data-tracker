from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Company, SpacEvent
from ..schemas import SpacEventOut

router = APIRouter(prefix="/api/spac-events", tags=["spac-events"])


@router.get("", response_model=list[SpacEventOut])
def list_spac_events(
    search: str | None = Query(None, description="Match against company name or ticker"),
    stage: str | None = Query(None, description="'ipo' or 'merger_completed'"),
    filed_from: date | None = Query(None, description="Only filings on/after this date"),
    filed_to: date | None = Query(None, description="Only filings on/before this date"),
    min_market_cap_millions: float | None = Query(
        None, description="Minimum market cap in $M; companies with no known market cap are excluded"
    ),
    limit: int | None = Query(None, description="Omit to return every matching event"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(SpacEvent).options(joinedload(SpacEvent.company)).join(Company)

    if search:
        like = f"%{search}%"
        query = query.filter((Company.name.ilike(like)) | (Company.ticker.ilike(like)))
    if stage:
        query = query.filter(SpacEvent.stage == stage)
    if filed_from:
        query = query.filter(SpacEvent.filing_date >= filed_from)
    if filed_to:
        query = query.filter(SpacEvent.filing_date <= filed_to)
    if min_market_cap_millions is not None:
        query = query.filter(Company.market_cap_usd >= min_market_cap_millions * 1_000_000)

    query = query.order_by(SpacEvent.filing_date.desc()).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()
