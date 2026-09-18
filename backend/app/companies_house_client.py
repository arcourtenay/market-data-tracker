"""Thin client for the UK Companies House public API.

Unlike the SEC tabs (which read from our database), the Companies House bidcos
tab queries Companies House live on every request, so the data is always current
without an ingestion step. The API key is read from COMPANIES_HOUSE_API_KEY.
"""

from __future__ import annotations

import concurrent.futures
from datetime import date

import requests

from .config import get_settings

API_BASE = "https://api.company-information.service.gov.uk"
WEB_BASE = "https://find-and-update.company-information.service.gov.uk"

_TIMEOUT = 20  # seconds
_PAGE_SIZE = 100  # Companies House advanced-search max page size
_DOC_WORKERS = 10  # concurrent filing-history lookups for incorporation docs

# A company's incorporation filing never changes once filed, so successful
# lookups are cached for the life of the process - this is the single biggest
# source of repeated, purely-redundant Companies House requests (one per
# company, per page load), and was routinely exhausting the 600-per-5-minutes
# rate limit on its own. Only successful lookups are cached; a transient
# failure falls through to the filing-history-page fallback WITHOUT being
# cached, so it's retried live next time rather than getting stuck.
_incorporation_doc_cache: dict[str, str] = {}


class CompaniesHouseError(RuntimeError):
    """Raised when Companies House cannot be reached or is misconfigured."""


def _auth() -> tuple[str, str]:
    key = get_settings().companies_house_api_key
    if not key:
        raise CompaniesHouseError(
            "COMPANIES_HOUSE_API_KEY is not set on the backend. Add it to backend/.env "
            "(local) or the service's environment variables (hosted)."
        )
    return (key, "")


def search_companies(
    name_includes: str,
    incorporated_from: date | None = None,
    incorporated_to: date | None = None,
    max_results: int = 2000,
) -> list[dict]:
    """Advanced-search for companies whose name includes ``name_includes``.

    Paginates through the *entire* result set for the window (up to ``max_results``
    as a safety cap) and returns the raw Companies House ``items`` dicts. Callers
    must sort/trim themselves: Companies House does not return results newest-first,
    so trimming before fetching every page would silently drop recent companies.
    """
    auth = _auth()
    results: list[dict] = []
    start_index = 0

    while len(results) < max_results:
        params: dict[str, object] = {
            "company_name_includes": name_includes,
            "size": _PAGE_SIZE,
            "start_index": start_index,
        }
        if incorporated_from:
            params["incorporated_from"] = incorporated_from.isoformat()
        if incorporated_to:
            params["incorporated_to"] = incorporated_to.isoformat()

        try:
            resp = requests.get(
                f"{API_BASE}/advanced-search/companies",
                auth=auth,
                params=params,
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise CompaniesHouseError(f"Could not reach Companies House: {exc}") from exc

        if resp.status_code == 416:
            # start_index past the end of the result set
            break
        if resp.status_code == 401:
            raise CompaniesHouseError("Companies House rejected the API key (401).")
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            raise CompaniesHouseError(f"Companies House returned {resp.status_code}") from exc

        items = resp.json().get("items", [])
        results.extend(items)
        if len(items) < _PAGE_SIZE:
            break
        start_index += _PAGE_SIZE

    return results[:max_results]


def incorporation_document_url(company_number: str) -> str:
    """Return a public link to a company's incorporation document.

    Looks up the incorporation filing to build a direct document link; falls back
    to the company's filing-history page if the specific filing can't be found.
    """
    cached = _incorporation_doc_cache.get(company_number)
    if cached is not None:
        return cached

    filing_history_page = f"{WEB_BASE}/company/{company_number}/filing-history"

    def _doc_url(txn: str) -> str:
        return (
            f"{WEB_BASE}/company/{company_number}/filing-history/"
            f"{txn}/document?format=pdf&download=0"
        )

    try:
        resp = requests.get(
            f"{API_BASE}/company/{company_number}/filing-history",
            auth=_auth(),
            params={"category": "incorporation"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        items = [i for i in resp.json().get("items", []) if i.get("transaction_id")]

        # The "incorporation" category also returns the memorandum & articles and
        # related resolutions. Prefer the actual incorporation filing (NEWINC /
        # "incorporation-company"); otherwise fall back to the first item.
        chosen = next(
            (item for item in items if item.get("type") == "NEWINC" or item.get("description") == "incorporation-company"),
            items[0] if items else None,
        )
        if chosen:
            url = _doc_url(chosen["transaction_id"])
            _incorporation_doc_cache[company_number] = url
            return url
    except (requests.RequestException, CompaniesHouseError):
        pass
    return filing_history_page


def incorporation_document_urls(company_numbers: list[str]) -> dict[str, str]:
    """Fetch incorporation-document links for many companies concurrently."""
    if not company_numbers:
        return {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=_DOC_WORKERS) as pool:
        return dict(
            zip(
                company_numbers,
                pool.map(incorporation_document_url, company_numbers),
            )
        )
