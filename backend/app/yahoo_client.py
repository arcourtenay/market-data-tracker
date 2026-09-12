"""Fetches live share price from Yahoo Finance's chart endpoint.

This endpoint is undocumented/unofficial - Yahoo could change or rate-limit it
without notice, and using it for automated fetching sits in a gray area of
Yahoo's terms of service. It's used here (instead of a paid market-data API)
because it needs no account or key, which fits a personal research tool; swap
in a licensed provider if that matters for your use case. Yahoo's own
market-cap/shares-outstanding fields now require an auth "crumb" this client
doesn't have, so only the price is read here - shares outstanding comes from
SEC XBRL instead (see app.enrich_market_cap).
"""

import time

import requests

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_MIN_INTERVAL_SECONDS = 0.3
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


class YahooClient:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._last_request_at = 0.0

    def get_price(self, symbol: str) -> float | None:
        """Returns the latest regular-market price, or None if unavailable
        (delisted ticker, no data, request failure, etc - all treated the same:
        we simply can't compute a market cap for this company right now)."""
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        try:
            response = self._session.get(_CHART_URL.format(symbol=symbol), timeout=15)
            self._last_request_at = time.monotonic()
            if response.status_code == 404:
                return None
            response.raise_for_status()
            result = response.json().get("chart", {}).get("result")
            if not result:
                return None
            return result[0].get("meta", {}).get("regularMarketPrice")
        except requests.RequestException:
            return None
