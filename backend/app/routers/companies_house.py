from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..companies_house_client import (
    CompaniesHouseError,
    incorporation_document_urls,
    search_companies,
)
from ..schemas import BidcoCompanyOut

router = APIRouter(prefix="/api/companies-house-bidcos", tags=["companies-house-bidcos"])


@router.get("", response_model=list[BidcoCompanyOut])
def list_bidcos(
    name_includes: str = Query(
        "bidco", description="Word that must appear in the company name (editable on the page)"
    ),
    incorporated_from: date | None = Query(
        None, description="Only companies incorporated on/after this date"
    ),
    incorporated_to: date | None = Query(
        None, description="Only companies incorporated on/before this date"
    ),
    max_results: int = Query(200, ge=1, le=500),
):
    """Live search of Companies House for companies whose name includes a keyword
    (default "bidco"), newest incorporations first, each with a link to its
    incorporation document."""
    keyword = name_includes.strip()
    if not keyword:
        raise HTTPException(status_code=422, detail="name_includes cannot be empty")

    try:
        companies = search_companies(
            keyword,
            incorporated_from=incorporated_from,
            incorporated_to=incorporated_to,
            max_results=max_results,
        )
    except CompaniesHouseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Newest incorporations first.
    companies.sort(key=lambda c: c.get("date_of_creation") or "", reverse=True)

    doc_urls = incorporation_document_urls([c["company_number"] for c in companies])

    results: list[BidcoCompanyOut] = []
    for co in companies:
        addr = co.get("registered_office_address", {}) or {}
        results.append(
            BidcoCompanyOut(
                company_name=co.get("company_name", ""),
                company_number=co["company_number"],
                date_of_creation=co.get("date_of_creation") or None,
                company_status=co.get("company_status"),
                locality=addr.get("locality"),
                postal_code=addr.get("postal_code"),
                country=addr.get("country"),
                incorporation_url=doc_urls.get(
                    co["company_number"], ""
                ),
            )
        )
    return results
