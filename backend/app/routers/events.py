from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Company, ManagementChangeEvent
from ..schemas import ManagementChangeEventOut

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[ManagementChangeEventOut])
def list_events(
    search: str | None = Query(None, description="Match against company name or ticker"),
    sic: str | None = Query(None, description="Filter by exact SIC code"),
    filed_from: date | None = Query(None, description="Only filings on/after this date"),
    filed_to: date | None = Query(None, description="Only filings on/before this date"),
    min_market_cap_millions: float | None = Query(
        None, description="Minimum market cap in $M; companies with no known market cap are excluded"
    ),
    limit: int | None = Query(None, description="Omit to return every matching event"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(ManagementChangeEvent).options(joinedload(ManagementChangeEvent.company)).join(Company)

    if search:
        like = f"%{search}%"
        query = query.filter((Company.name.ilike(like)) | (Company.ticker.ilike(like)))
    if sic:
        query = query.filter(Company.sic == sic)
    if filed_from:
        query = query.filter(ManagementChangeEvent.filing_date >= filed_from)
    if filed_to:
        query = query.filter(ManagementChangeEvent.filing_date <= filed_to)
    if min_market_cap_millions is not None:
        query = query.filter(Company.market_cap_usd >= min_market_cap_millions * 1_000_000)

    query = query.order_by(ManagementChangeEvent.filing_date.desc()).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


@router.get("/{event_id}", response_model=ManagementChangeEventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = (
        db.query(ManagementChangeEvent)
        .options(joinedload(ManagementChangeEvent.company))
        .filter(ManagementChangeEvent.id == event_id)
        .one_or_none()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
