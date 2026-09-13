from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Company, IpoEvent
from ..schemas import IpoEventOut

router = APIRouter(prefix="/api/ipo-events", tags=["ipo-events"])


@router.get("", response_model=list[IpoEventOut])
def list_ipo_events(
    search: str | None = Query(None, description="Match against company name or ticker"),
    filed_from: date | None = Query(None, description="Only filings on/after this date"),
    filed_to: date | None = Query(None, description="Only filings on/before this date"),
    limit: int | None = Query(None, description="Omit to return every matching event"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(IpoEvent).options(joinedload(IpoEvent.company)).join(Company)

    if search:
        like = f"%{search}%"
        query = query.filter((Company.name.ilike(like)) | (Company.ticker.ilike(like)))
    if filed_from:
        query = query.filter(IpoEvent.filing_date >= filed_from)
    if filed_to:
        query = query.filter(IpoEvent.filing_date <= filed_to)

    query = query.order_by(IpoEvent.filing_date.desc()).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()
