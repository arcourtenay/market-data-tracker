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
    ipo_proceeds_usd: float | None
    market_cap_usd: float | None


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


class IpoEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    accession_no: str
    form_type: str
    stage: str
    filing_date: date
    report_date: date | None
    filing_url: str
    created_at: datetime
    company: CompanyOut


class DirectorBuyEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reporting_owner_name: str
    officer_title: str | None
    transaction_date: date
    filing_date: date
    shares: float
    price_per_share: float
    value_usd: float
    filing_url: str
    created_at: datetime
    company: CompanyOut


class FinancialResultEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    accession_no: str
    form_type: str
    filing_date: date
    filing_url: str
    created_at: datetime
    company: CompanyOut


class BidcoCompanyOut(BaseModel):
    company_name: str
    company_number: str
    date_of_creation: date | None
    company_status: str | None
    locality: str | None
    postal_code: str | None
    country: str | None
    incorporation_url: str


class TakeoverEntryOut(BaseModel):
    offeree: str
    offeree_lei: str | None
    offer_period_commenced: str | None
    offerors: list[str]
    detail_lines: list[str]


class TakeoverChangesOut(BaseModel):
    since_date: date | None
    as_of: datetime
    additions: list[TakeoverEntryOut]
    deletions: list[TakeoverEntryOut]
    current_count: int
    baseline_count: int | None
    note: str | None


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
    prior_period_of_report: date | None
    filing_date: date
    total_value_usd: float
    holdings: list[FundHoldingOut]
