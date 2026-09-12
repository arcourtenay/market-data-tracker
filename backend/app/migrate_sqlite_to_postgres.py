"""One-off: copies all data from the local sec_tracker.db (SQLite) into a
Postgres database, for moving from local dev to a hosted deployment.

Run this once, locally, after your hosted Postgres instance exists (e.g. the
Render database from render.yaml) and before pointing the deployed backend at
it. Safe to re-run: uses INSERT ... ON CONFLICT DO NOTHING, so re-running
just skips rows already copied.

Inserts in batches (not one row at a time) since the target is a remote
database - a network round trip per row would take hours across ~80,000 rows.

Usage:
    python -m app.migrate_sqlite_to_postgres "postgresql://user:pass@host:5432/dbname"
"""

import sys

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from .database import Base
from .models import Company, ManagementChangeEvent

_BATCH_SIZE = 1000


def _reset_id_sequence(pg_session, table_name: str) -> None:
    """Copying rows with explicit ids doesn't advance Postgres's auto-increment
    sequence, so without this the next real INSERT from the app would collide
    with an id we just copied in."""
    pg_session.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table_name}), 1))"
        )
    )
    pg_session.commit()


def _copy_table(sqlite_session, pg_session, model) -> int:
    rows = sqlite_session.query(model).all()
    columns = [c.name for c in model.__table__.columns]
    total = len(rows)

    for start in range(0, total, _BATCH_SIZE):
        batch = rows[start : start + _BATCH_SIZE]
        values = [{col: getattr(row, col) for col in columns} for row in batch]
        stmt = pg_insert(model).values(values).on_conflict_do_nothing(index_elements=["id"])
        pg_session.execute(stmt)
        pg_session.commit()
        print(f"  {min(start + _BATCH_SIZE, total)}/{total}")

    return total


def run(postgres_url: str) -> None:
    sqlite_engine = create_engine("sqlite:///./sec_tracker.db")
    pg_engine = create_engine(postgres_url)

    Base.metadata.create_all(bind=pg_engine)

    SqliteSession = sessionmaker(bind=sqlite_engine)
    PgSession = sessionmaker(bind=pg_engine)

    with SqliteSession() as sqlite_session, PgSession() as pg_session:
        print("Copying companies...")
        companies_copied = _copy_table(sqlite_session, pg_session, Company)
        _reset_id_sequence(pg_session, "companies")
        print(f"Copied {companies_copied} companies")

        print("Copying management-change events...")
        events_copied = _copy_table(sqlite_session, pg_session, ManagementChangeEvent)
        _reset_id_sequence(pg_session, "management_change_events")
        print(f"Copied {events_copied} management-change events")

    print("Done. Point DATABASE_URL at this Postgres instance to use it.")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1])


if __name__ == "__main__":
    main()
