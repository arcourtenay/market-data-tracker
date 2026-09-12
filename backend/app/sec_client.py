"""Thin client for the SEC EDGAR APIs.

SEC's fair-access policy requires every request to carry a descriptive
User-Agent ("<company/app name> <contact email>") and asks that automated
callers stay under ~10 requests/second. This client sets that header from
config and self-throttles well under the limit.
"""

import time
from datetime import date

import requests

from .config import get_settings

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
_COMPANY_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/{taxonomy}/{tag}.json"
_DAILY_INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/master.{yyyymmdd}.idx"

_MIN_INTERVAL_SECONDS = 0.15  # ~6-7 req/sec, safely under SEC's ~10 req/sec guidance


class SecClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": settings.sec_user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self._last_request_at = 0.0

    def _throttled_get(self, url: str) -> requests.Response:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        response = self._session.get(url, timeout=30)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response

    def get_company_tickers(self) -> dict:
        """Returns the SEC's full ticker->CIK map, keyed by an arbitrary index."""
        return self._throttled_get(_TICKERS_URL).json()

    def get_submissions(self, cik10: str) -> dict:
        """Returns a company's filing history (recent filings inline, older ones paginated)."""
        return self._throttled_get(_SUBMISSIONS_URL.format(cik10=cik10)).json()

    def get_text(self, url: str) -> str:
        """Fetches an arbitrary sec.gov document (e.g. a filing) as text."""
        return self._throttled_get(url).text

    def get_json(self, url: str) -> dict:
        """Fetches an arbitrary sec.gov JSON document (e.g. a filing's index.json)."""
        return self._throttled_get(url).json()

    def get_company_concept(self, cik10: str, taxonomy: str, tag: str) -> dict | None:
        """Returns one XBRL concept's reported values for a company, or None if the
        company has never reported it (a normal, common case - not an error)."""
        url = _COMPANY_CONCEPT_URL.format(cik10=cik10, taxonomy=taxonomy, tag=tag)
        try:
            return self._throttled_get(url).json()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    def get_daily_index(self, day: date) -> list[dict]:
        """Returns every filing SEC's daily index lists for this date (CIK, name,
        form, filename), across ALL filers - the fast way to find "what got filed
        today" without asking each of the ~10,000+ companies individually.

        Returns [] for a date with no index yet (today's, before SEC publishes it)
        or none at all (weekends/holidays) - not an error, just nothing filed."""
        quarter = (day.month - 1) // 3 + 1
        url = _DAILY_INDEX_URL.format(year=day.year, quarter=quarter, yyyymmdd=day.strftime("%Y%m%d"))
        try:
            text = self._throttled_get(url).text
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (403, 404):
                return []
            raise

        lines = text.splitlines()
        try:
            separator_idx = next(i for i, line in enumerate(lines) if set(line.strip()) == {"-"})
        except StopIteration:
            return []

        entries = []
        for line in lines[separator_idx + 1 :]:
            parts = line.split("|")
            if len(parts) != 5:
                continue
            cik, name, form, date_filed, filename = parts
            entries.append(
                {
                    "cik10": cik.strip().zfill(10),
                    "name": name.strip(),
                    "form": form.strip(),
                    "filename": filename.strip(),
                }
            )
        return entries


def build_filing_url(cik: str, accession_no: str, primary_document: str | None) -> str:
    cik_no_zeros = str(int(cik))
    accession_no_nodashes = accession_no.replace("-", "")
    if primary_document:
        return (
            f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/"
            f"{accession_no_nodashes}/{primary_document}"
        )
    return f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_nodashes}/"
