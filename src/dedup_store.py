import logging
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

_SCHEMA = "county_records"
_TABLE = "seen_records"


def _engine():
    url = os.environ["COUNTY_RECORDS_DATABASE_URL"]
    return create_engine(url, poolclass=NullPool)


def init_store() -> None:
    """Create the schema and seen_records table if they don't already exist."""
    with _engine().begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}"))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {_SCHEMA}.{_TABLE} (
                county           TEXT NOT NULL,
                instrument_number TEXT NOT NULL,
                seen_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (county, instrument_number)
            )
        """))
    logger.info("Dedup store initialized (%s.%s)", _SCHEMA, _TABLE)


def is_new(county: str, instrument_number: str) -> bool:
    """Return True if this record has not been seen before."""
    with _engine().connect() as conn:
        result = conn.execute(
            text(f"SELECT 1 FROM {_SCHEMA}.{_TABLE} WHERE county = :county AND instrument_number = :instr"),
            {"county": county, "instr": instrument_number},
        )
        return result.fetchone() is None


def mark_seen(county: str, instrument_number: str) -> None:
    """Record this instrument as seen so it won't be re-processed."""
    with _engine().begin() as conn:
        conn.execute(
            text(f"""
                INSERT INTO {_SCHEMA}.{_TABLE} (county, instrument_number, seen_at)
                VALUES (:county, :instr, :seen_at)
                ON CONFLICT (county, instrument_number) DO NOTHING
            """),
            {"county": county, "instr": instrument_number, "seen_at": datetime.now(timezone.utc)},
        )


def filter_new_records(records: list[dict]) -> list[dict]:
    """Return only records that have not been seen before.

    Args:
        records: Records from county scrapers (already filtered by doc type).

    Returns:
        Subset of records that are new (not yet in the seen_records table).
    """
    new_records = []
    for record in records:
        county = record.get("county", "")
        instrument = record.get("instrument_number", "")
        if not instrument:
            logger.warning("Record missing instrument_number — skipping dedup check: %s", record)
            new_records.append(record)
            continue
        if is_new(county, instrument):
            new_records.append(record)

    logger.info("Dedup: %d new out of %d records", len(new_records), len(records))
    return new_records


def mark_all_seen(records: list[dict]) -> None:
    """Mark a batch of records as seen after successful processing."""
    for record in records:
        county = record.get("county", "")
        instrument = record.get("instrument_number", "")
        if county and instrument:
            mark_seen(county, instrument)
