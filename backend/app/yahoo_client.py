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
from datetime import date, datetime, timedelta, timezone

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

    def get_price_on_date(self, symbol: str, target_date: date) -> float | None:
        """Returns the closing price nearest to `target_date` (a several-day
        window either side, to land on the nearest actual trading day across
        weekends/holidays), or None if unavailable. Used to estimate a dollar
        value for an activist stake change where SEC's own data gives only a
        share count, not a transaction price like Form 4 does."""
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        start = datetime.combine(target_date - timedelta(days=5), datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(target_date + timedelta(days=5), datetime.min.time(), tzinfo=timezone.utc)
        try:
            response = self._session.get(
                _CHART_URL.format(symbol=symbol),
                params={"period1": int(start.timestamp()), "period2": int(end.timestamp()), "interval": "1d"},
                timeout=15,
            )
            self._last_request_at = time.monotonic()
            if response.status_code == 404:
                return None
            response.raise_for_status()
            result = response.json().get("chart", {}).get("result")
            if not result:
                return None
            timestamps = result[0].get("timestamp") or []
            closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close") or []
            candidates = [
                (abs((datetime.fromtimestamp(ts, tz=timezone.utc).date() - target_date).days), close)
                for ts, close in zip(timestamps, closes)
                if close is not None
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda c: c[0])
            return candidates[0][1]
        except requests.RequestException:
            return None
