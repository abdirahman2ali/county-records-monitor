import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load shared credentials first, then project-local overrides
load_dotenv(Path(__file__).resolve().parents[2] / ".claude" / ".env")
load_dotenv()

from src.dedup_store import filter_new_records, init_store, mark_all_seen
from src.notifier import send_weekly_digest
from src.record_filter import filter_records
from src.scorer import score_record
from src.scrapers.broward import fetch_new_records as broward_fetch
from src.scrapers.miami_dade import fetch_new_records as miami_dade_fetch
from src.scrapers.palm_beach import fetch_new_records as palm_beach_fetch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_REQUIRED_ENV = [
    "ANTHROPIC_API_KEY",
    "COUNTY_RECORDS_DATABASE_URL",
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    "ALERT_EMAIL",
]


def _validate_env() -> None:
    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        logger.error("Missing required environment variables: %s", missing)
        sys.exit(1)


def main() -> None:
    _validate_env()

    # --- 1. Fetch records ---
    to_date = date.today()
    from_date = to_date - timedelta(days=7)
    logger.info("Scanning records from %s to %s", from_date, to_date)

    raw_records: list[dict] = []
    for name, fetch_fn in [
        ("Broward", broward_fetch),
        ("Miami-Dade", miami_dade_fetch),
        ("Palm Beach", palm_beach_fetch),
    ]:
        try:
            records = fetch_fn(from_date, to_date)
            logger.info("%s: %d raw records fetched", name, len(records))
            raw_records.extend(records)
        except Exception as e:
            logger.error("%s scraper failed: %s", name, e)

    if not raw_records:
        logger.warning("No records fetched from any county — check scrapers")
        print("Done: 0 records fetched. Check logs for scraper errors.")
        return

    # --- 2. Filter to distress-related doc types ---
    distress_records = filter_records(raw_records)
    logger.info("After filter: %d distress records from %d raw", len(distress_records), len(raw_records))

    # --- 3. Dedup against Postgres ---
    init_store()
    new_records = filter_new_records(distress_records)
    logger.info("After dedup: %d new records to process", len(new_records))

    if not new_records:
        logger.info("No new records this run")
        print("Done: 0 new records. Nothing to process.")
        return

    # --- 4. Score each record ---
    scored: list[tuple[dict, int, str, str]] = []
    for record in new_records:
        try:
            score, lead_type, outreach_note = score_record(record)
            scored.append((record, score, lead_type, outreach_note))
        except Exception as e:
            logger.error("Failed to score record %s: %s", record.get("instrument_number"), e)

    # --- 5. Mark processed records as seen ---
    mark_all_seen([r for r, *_ in scored])

    # --- 6. Send email digest ---
    send_weekly_digest(scored)

    high_priority = sum(1 for _, score, *_ in scored if score >= 7)
    print(
        f"\nDone: {len(new_records)} new records processed, "
        f"{high_priority} high priority (score >= 7)."
    )


if __name__ == "__main__":
    main()
