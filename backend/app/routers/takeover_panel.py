from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import TakeoverSnapshot
from ..schemas import TakeoverChangesOut, TakeoverEntryOut
from ..takeover_panel_client import (
    TakeoverEntry,
    TakeoverPanelError,
    diff_entries,
    fetch_csv,
    parse_entries,
)

router = APIRouter(prefix="/api/takeover-panel-changes", tags=["takeover-panel-changes"])

# The disclosure table is a UK publication, so "today" is measured in UK local time.
LONDON = ZoneInfo("Europe/London")


def _to_out(entry: TakeoverEntry) -> TakeoverEntryOut:
    return TakeoverEntryOut(
        offeree=entry.offeree,
        offeree_lei=entry.offeree_lei,
        offer_period_commenced=entry.offer_period_commenced,
        offerors=entry.offerors,
        detail_lines=entry.detail_lines,
    )


@router.get("", response_model=TakeoverChangesOut)
def get_changes(db: Session = Depends(get_db)):
    """Fetch the live disclosure table and report additions/deletions versus the
    most recent snapshot stored on an earlier day ("changes since X date").

    Refreshing several times in one day does not move the comparison date: the
    baseline is always the latest snapshot from a day *before* today. Today's
    fetch is stored as today's snapshot, which becomes the baseline tomorrow."""
    try:
        csv_text = fetch_csv()
    except TakeoverPanelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    current_entries = parse_entries(csv_text)
    now = datetime.now(LONDON)
    today = now.date()

    # Baseline: the most recent snapshot from a day strictly before today. Read
    # its values now, before the commit below can expire the ORM instance.
    baseline_snap = (
        db.query(TakeoverSnapshot)
        .filter(TakeoverSnapshot.snapshot_date < today)
        .order_by(TakeoverSnapshot.snapshot_date.desc())
        .first()
    )
    baseline_date = baseline_snap.snapshot_date if baseline_snap else None
    baseline_csv = baseline_snap.csv_text if baseline_snap else None

    # Upsert today's snapshot (latest fetch of the day wins). This does not affect
    # the baseline above, which excludes today.
    today_snap = (
        db.query(TakeoverSnapshot)
        .filter(TakeoverSnapshot.snapshot_date == today)
        .first()
    )
    if today_snap:
        today_snap.csv_text = csv_text
    else:
        db.add(TakeoverSnapshot(snapshot_date=today, csv_text=csv_text))
    try:
        db.commit()
    except IntegrityError:
        # Another concurrent request inserted today's row first; that's fine.
        db.rollback()

    if baseline_csv is None:
        return TakeoverChangesOut(
            since_date=None,
            as_of=now,
            additions=[],
            deletions=[],
            current_count=len(current_entries),
            baseline_count=None,
            note=(
                "First snapshot stored. Additions and deletions will appear once "
                "the table is refreshed on a later day."
            ),
        )

    baseline_entries = parse_entries(baseline_csv)
    additions, deletions = diff_entries(baseline_entries, current_entries)

    return TakeoverChangesOut(
        since_date=baseline_date,
        as_of=now,
        additions=[_to_out(e) for e in additions],
        deletions=[_to_out(e) for e in deletions],
        current_count=len(current_entries),
        baseline_count=len(baseline_entries),
        note=None,
    )
