from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    ticker: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    sic: Mapped[str | None] = mapped_column(String(10), index=True, nullable=True)
    sic_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Shares outstanding from SEC XBRL (dei:EntityCommonStockSharesOutstanding, from the most
    # recent 10-Q/10-K cover page) - changes rarely, so shares_outstanding_checked_at gates a
    # one-time-per-company lookup rather than refetching every run.
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    shares_outstanding_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # market_cap_usd = shares_outstanding x latest Yahoo Finance price. Recomputed on every
    # app.enrich_market_cap run (for companies with a ticker), so this stays close to live.
    market_cap_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    events: Mapped[list["ManagementChangeEvent"]] = relationship(back_populates="company")
    spac_events: Mapped[list["SpacEvent"]] = relationship(back_populates="company")


class ManagementChangeEvent(Base):
    __tablename__ = "management_change_events"
    __table_args__ = (UniqueConstraint("accession_no", name="uq_event_accession_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    accession_no: Mapped[str] = mapped_column(String(25), index=True)
    form_type: Mapped[str] = mapped_column(String(20))
    items: Mapped[str] = mapped_column(String(100))
    filing_date: Mapped[date] = mapped_column(Date, index=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filing_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # NULL = not yet processed by app.extract_people; "" = processed, no names found.
    people: Mapped[str | None] = mapped_column(String(500), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="events")


class SpacEvent(Base):
    """A SPAC lifecycle event: either its IPO (stage='ipo', signaled by a 424B4
    prospectus from a SIC-6770 'Blank Check' company) or its de-SPAC merger
    completion (stage='merger_completed', signaled by an 8-K Item 5.06 'Change
    in Shell Company Status')."""

    __tablename__ = "spac_events"
    __table_args__ = (UniqueConstraint("accession_no", name="uq_spac_event_accession_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    accession_no: Mapped[str] = mapped_column(String(25), index=True)
    form_type: Mapped[str] = mapped_column(String(20))
    items: Mapped[str] = mapped_column(String(100))
    stage: Mapped[str] = mapped_column(String(20), index=True)
    filing_date: Mapped[date] = mapped_column(Date, index=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filing_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="spac_events")
