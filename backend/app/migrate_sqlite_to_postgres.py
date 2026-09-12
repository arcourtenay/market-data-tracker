"""One-off: copies all data from the local sec_tracker.db (SQLite) into a
Postgres database, for moving from local dev to a hosted deployment.

Run this once, locally, after your hosted Postgres instance exists (e.g. the
Render database from render.yaml) and before pointing the deployed backend at
it. Safe to re-run: uses INSERT ... ON CONFLICT DO NOTHING, so re-running
just skips rows already copied.

Usage:
    python -m app.migrate_sqlite_to_postgres "postgresql://user:pass@host:5432/dbname"
"""

import sys

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from .database import Base
from .models import Company, ManagementChangeEvent


def _copy_table(sqlite_session, pg_session, model) -> int:
    rows = sqlite_session.query(model).all()
    count = 0
    for row in rows:
        data = {c.name: getattr(row, c.name) for c in model.__table__.columns}
        stmt = pg_insert(model).values(**data).on_conflict_do_nothing(index_elements=["id"])
        pg_session.execute(stmt)
        count += 1
    pg_session.commit()
    return count


def run(postgres_url: str) -> None:
    sqlite_engine = create_engine("sqlite:///./sec_tracker.db")
    pg_engine = create_engine(postgres_url)

    Base.metadata.create_all(bind=pg_engine)

    SqliteSession = sessionmaker(bind=sqlite_engine)
    PgSession = sessionmaker(bind=pg_engine)

    with SqliteSession() as sqlite_session, PgSession() as pg_session:
        companies_copied = _copy_table(sqlite_session, pg_session, Company)
        print(f"Copied {companies_copied} companies")
        events_copied = _copy_table(sqlite_session, pg_session, ManagementChangeEvent)
        print(f"Copied {events_copied} management-change events")

    print("Done. Point DATABASE_URL at this Postgres instance to use it.")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1])


if __name__ == "__main__":
    main()
