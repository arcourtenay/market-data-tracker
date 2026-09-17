"""Fetches and parses the UK Takeover Panel disclosure-table CSV.

The CSV is a formatted document, not a flat table: a header, a "today's changes"
section, then a ``DISCLOSURE TABLE`` marker followed by one block per offeree
(offer period, share classes, offeror(s), deadlines), and finally a ``Notes:``
footer. We parse the blocks between ``DISCLOSURE TABLE`` and ``Notes:`` into one
entry per offeree, keyed by offeree name, so two snapshots can be diffed for
additions and deletions.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import requests

CSV_URL = "https://www.thetakeoverpanel.org.uk/new/disclosuretable/v3/disclosuretable.csv"
_TIMEOUT = 30

_TABLE_MARKER = "DISCLOSURE TABLE"
_NOTES_MARKER = "notes:"
_OFFEREE_PREFIX = "OFFEREE:"
_OFFEROR_PREFIX = "OFFEROR:"
_COMMENCED_PREFIX = "Offer period commenced:"
_LEI_PREFIX = "LEI:"


class TakeoverPanelError(RuntimeError):
    """Raised when the disclosure table cannot be fetched."""


@dataclass
class TakeoverEntry:
    offeree: str
    offeree_lei: str | None = None
    offer_period_commenced: str | None = None
    offerors: list[str] = field(default_factory=list)
    detail_lines: list[str] = field(default_factory=list)


def fetch_csv() -> str:
    """Download the current disclosure-table CSV (follows the site's redirect)."""
    try:
        resp = requests.get(CSV_URL, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise TakeoverPanelError(
            f"Could not fetch the Takeover Panel disclosure table: {exc}"
        ) from exc
    return resp.text


def parse_entries(csv_text: str) -> dict[str, TakeoverEntry]:
    """Parse the disclosure-table section into {offeree_name: TakeoverEntry}."""
    entries: dict[str, TakeoverEntry] = {}
    in_table = False
    current: TakeoverEntry | None = None

    for row in csv.reader(io.StringIO(csv_text)):
        cell0 = row[0].strip() if row else ""

        if not in_table:
            if cell0 == _TABLE_MARKER:
                in_table = True
            continue

        if cell0.lower().startswith(_NOTES_MARKER):
            break

        if cell0.startswith(_OFFEREE_PREFIX):
            offeree = cell0[len(_OFFEREE_PREFIX):].strip()
            lei = None
            for cell in row[1:]:
                text = cell.strip()
                if text.startswith(_LEI_PREFIX):
                    lei = text[len(_LEI_PREFIX):].strip() or None
            current = TakeoverEntry(offeree=offeree, offeree_lei=lei)
            entries[offeree] = current
        elif current is not None:
            joined = " | ".join(cell.strip() for cell in row if cell.strip())
            if not joined:
                continue
            if cell0.startswith(_COMMENCED_PREFIX):
                current.offer_period_commenced = cell0[len(_COMMENCED_PREFIX):].strip()
            if cell0.startswith(_OFFEROR_PREFIX):
                current.offerors.append(cell0[len(_OFFEROR_PREFIX):].strip())
            current.detail_lines.append(joined)

    return entries


def diff_entries(
    baseline: dict[str, TakeoverEntry], current: dict[str, TakeoverEntry]
) -> tuple[list[TakeoverEntry], list[TakeoverEntry]]:
    """Return (additions, deletions): entries new in ``current`` and entries
    removed from ``baseline``, each sorted by offeree name."""
    additions = [entry for key, entry in current.items() if key not in baseline]
    deletions = [entry for key, entry in baseline.items() if key not in current]
    additions.sort(key=lambda e: e.offeree.lower())
    deletions.sort(key=lambda e: e.offeree.lower())
    return additions, deletions
