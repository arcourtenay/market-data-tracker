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


class FundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cik: str
    name: str


class FundHoldingOut(BaseModel):
    issuer_name: str
    cusip: str
    value_usd: float
    shares: float
    share_class: str | None
    weight_pct: float
    share_change_pct: float | None


class FundHoldingsOut(BaseModel):
    fund: FundOut
    period_of_report: date
    filing_date: date
    total_value_usd: float
    holdings: list[FundHoldingOut]
