from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
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

    # IPO proceeds from SEC XBRL (us-gaap:ProceedsFromIssuanceInitialPublicOffering or
    # ProceedsFromIssuanceOfCommonStock, whichever the filer used), for companies with an IPO
    # or SPAC-IPO event. Usually not available until the company's first post-IPO 10-Q/10-K -
    # left null (and retried on each app.enrich_market_cap run) until then, a one-time fixed
    # historical fact once found.
    ipo_proceeds_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    spac_events: Mapped[list["SpacEvent"]] = relationship(back_populates="company")
    ipo_events: Mapped[list["IpoEvent"]] = relationship(back_populates="company")
    director_buy_events: Mapped[list["DirectorBuyEvent"]] = relationship(back_populates="company")
    financial_result_events: Mapped[list["FinancialResultEvent"]] = relationship(back_populates="company")


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


class IpoEvent(Base):
    """A non-SPAC company's IPO lifecycle event, for a company whose SIC code
    isn't 6770 ('Blank Checks', i.e. not a SPAC - those are tracked as
    SpacEvents instead):

      - stage='s1_filed': the company's EARLIEST visible Form S-1 (the
        standard IPO registration statement, filed before a company is
        subject to SEC reporting requirements) - i.e. it has registered to
        go public but not yet priced.
      - stage='priced': the company's EARLIEST visible Form 424B4 (final IPO
        prospectus), gated on the company's history also containing a Form
        S-1 - i.e. the IPO has priced and started trading.

    Both use "earliest visible" rather than "any" to exclude routine
    follow-on/shelf S-1 or 424B4 refilings by already-public small-caps."""

    __tablename__ = "ipo_events"
    __table_args__ = (UniqueConstraint("accession_no", name="uq_ipo_event_accession_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    accession_no: Mapped[str] = mapped_column(String(25), index=True)
    form_type: Mapped[str] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(20), index=True)
    filing_date: Mapped[date] = mapped_column(Date, index=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filing_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="ipo_events")


class DirectorBuyEvent(Base):
    """An open-market purchase of common stock by a company director,
    disclosed on Form 4 (Statement of Changes in Beneficial Ownership):
    transactionCode 'P' (open market purchase) with
    transactionAcquiredDisposedCode 'A' (acquired), by a reporting owner
    with isDirector=true. Officer-only or 10%-owner-only filers, and
    non-purchase codes (grants, gifts, option exercises, sales), are
    excluded - this tracks directors buying on the open market specifically.

    A single Form 4 can report several qualifying transactions (line_no
    distinguishes them) - and, rarely, more than one reporting owner on a
    joint filing, in which case only the first-listed owner is used."""

    __tablename__ = "director_buy_events"
    __table_args__ = (UniqueConstraint("accession_no", "line_no", name="uq_director_buy_accession_line"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    accession_no: Mapped[str] = mapped_column(String(25), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    reporting_owner_name: Mapped[str] = mapped_column(String(255))
    officer_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    filing_date: Mapped[date] = mapped_column(Date, index=True)
    shares: Mapped[float] = mapped_column(Float)
    price_per_share: Mapped[float] = mapped_column(Float)
    value_usd: Mapped[float] = mapped_column(Float)
    filing_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="director_buy_events")


class FinancialResultEvent(Base):
    """A periodic financial report (Form 10-K or 10-Q, including amendments)
    filed by any SEC reporting company - a pure rolling feed straight off
    SEC's daily index, not a per-company history scan, since every 10-K/10-Q
    is inherently relevant (there's no "first ever" signal to detect here
    the way there is for SPAC/IPO events)."""

    __tablename__ = "financial_result_events"
    __table_args__ = (UniqueConstraint("accession_no", name="uq_financial_result_accession_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    accession_no: Mapped[str] = mapped_column(String(25), index=True)
    form_type: Mapped[str] = mapped_column(String(20))
    filing_date: Mapped[date] = mapped_column(Date, index=True)
    filing_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="financial_result_events")


class Fund(Base):
    """An institutional manager we track 13F holdings for, picked by CIK
    (not auto-discovered - added one at a time as the user names one)."""

    __tablename__ = "funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    holdings: Mapped[list["FundHolding"]] = relationship(back_populates="fund", cascade="all, delete-orphan")


class FundHolding(Base):
    """One line of a fund's LATEST Form 13F-HR information table. Only the most
    recent filing is kept - re-ingesting a fund replaces its holdings wholesale
    rather than accumulating history."""

    __tablename__ = "fund_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), index=True)
    accession_no: Mapped[str] = mapped_column(String(25), index=True)
    period_of_report: Mapped[date] = mapped_column(Date, index=True)
    filing_date: Mapped[date] = mapped_column(Date)
    issuer_name: Mapped[str] = mapped_column(String(255))
    cusip: Mapped[str] = mapped_column(String(20))
    value_usd: Mapped[float] = mapped_column(Float)
    shares: Mapped[float] = mapped_column(Float)
    share_class: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    fund: Mapped["Fund"] = relationship(back_populates="holdings")
