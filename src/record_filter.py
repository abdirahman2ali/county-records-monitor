import logging

logger = logging.getLogger(__name__)

# Keywords that must appear in the doc_type field to qualify as a distress lead.
# Matching is case-insensitive substring — covers variations across county portals.
_DISTRESS_KEYWORDS = [
    "LIS PENDENS",
    "FORECLOSURE",
    "PROBATE",
    "DEATH",
    "DISSOLUTION",
    "DIVORCE",
    "PERSONAL REPRESENTATIVE",
    "CERTIFICATE OF TITLE",
    "NOTICE OF DEFAULT",
    "NOTICE OF SALE",
]


def is_distress_record(record: dict) -> bool:
    """Return True if the record's doc_type matches any distress keyword."""
    doc_type = (record.get("doc_type") or "").upper()
    return any(kw in doc_type for kw in _DISTRESS_KEYWORDS)


def filter_records(records: list[dict]) -> list[dict]:
    """Filter a list of raw county records down to distress-related filings.

    Args:
        records: Raw records from any county scraper.

    Returns:
        Filtered list containing only distress records.
    """
    matched = [r for r in records if is_distress_record(r)]
    skipped = len(records) - len(matched)
    if skipped:
        logger.debug("Filtered out %d non-distress records", skipped)
    return matched
