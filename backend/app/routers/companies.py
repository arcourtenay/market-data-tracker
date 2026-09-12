from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Company
from ..schemas import CompanyOut

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=list[CompanyOut])
def list_companies(
    search: str | None = Query(None, description="Match against company name or ticker"),
    sic: str | None = Query(None, description="Filter by exact SIC code"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Company)
    if search:
        like = f"%{search}%"
        query = query.filter((Company.name.ilike(like)) | (Company.ticker.ilike(like)))
    if sic:
        query = query.filter(Company.sic == sic)
    return query.order_by(Company.name).offset(offset).limit(limit).all()
