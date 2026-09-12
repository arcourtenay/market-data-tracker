from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cik: str
    name: str
    ticker: str | None
    sic: str | None
    sic_description: str | None


class ManagementChangeEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    accession_no: str
    form_type: str
    items: str
    filing_date: date
    report_date: date | None
    primary_document: str | None
    filing_url: str
    created_at: datetime
    people: str | None
    company: CompanyOut


class SpacEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    accession_no: str
    form_type: str
    items: str
    stage: str
    filing_date: date
    report_date: date | None
    filing_url: str
    created_at: datetime
    company: CompanyOut
