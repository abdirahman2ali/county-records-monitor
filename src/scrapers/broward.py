import logging
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Broward County Official Records search portal
# Verify current URL at: https://www.broward.org/RecordsTaxesTreasury/RecordingAndDocuments
_BASE_URL = "https://official.broward.org"
_SEARCH_URL = f"{_BASE_URL}/records/search.aspx"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}

# Document type codes used by the Broward portal — verify against the portal's dropdown
_TARGET_DOC_TYPES = [
    "LIS PENDENS",
    "NOTICE OF LIS PENDENS",
    "FORECLOSURE",
    "PROBATE",
    "DEATH CERTIFICATE",
    "PERSONAL REPRESENTATIVE DEED",
    "CERTIFICATE OF TITLE",
    "DISSOLUTION OF MARRIAGE",
]


def _get_viewstate(session: requests.Session) -> tuple[str, str]:
    """Fetch the search page and extract ASP.NET ViewState tokens."""
    resp = session.get(_SEARCH_URL, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    viewstate = soup.find("input", {"id": "__VIEWSTATE"})
    eventvalidation = soup.find("input", {"id": "__EVENTVALIDATION"})
    return (
        viewstate["value"] if viewstate else "",
        eventvalidation["value"] if eventvalidation else "",
    )


def _parse_results(html: str) -> list[dict]:
    """Parse the search results HTML table into a list of record dicts."""
    soup = BeautifulSoup(html, "html.parser")
    records = []

    # Results are typically in a table with id containing "GridView" or "Results"
    table = soup.find("table", {"id": lambda x: x and ("grid" in x.lower() or "result" in x.lower())})
    if table is None:
        # Fallback: look for any data table
        table = soup.find("table", class_=lambda x: x and "result" in (x or "").lower())

    if table is None:
        logger.debug("No results table found in Broward response")
        return records

    rows = table.find_all("tr")
    headers = [th.get_text(strip=True).upper() for th in rows[0].find_all(["th", "td"])] if rows else []

    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cells or len(cells) < 3:
            continue

        # Map cells to fields using header positions; fall back to positional
        def cell(name: str, pos: int) -> str:
            try:
                idx = next(i for i, h in enumerate(headers) if name in h)
                return cells[idx] if idx < len(cells) else ""
            except StopIteration:
                return cells[pos] if pos < len(cells) else ""

        records.append({
            "county": "Broward",
            "instrument_number": cell("INSTRUMENT", 0),
            "doc_type": cell("DOC", 1).upper(),
            "recorded_date": cell("RECORDED", 2),
            "grantor": cell("GRANTOR", 3),
            "grantee": cell("GRANTEE", 4),
            "property_address": cell("ADDRESS", 5),
            "property_city": cell("CITY", 6),
            "zip_code": cell("ZIP", 7),
            "parcel_number": cell("PARCEL", 8),
            "book_page": cell("BOOK", 9),
        })

    return records


def fetch_new_records(from_date: date, to_date: date) -> list[dict]:
    """Fetch Broward County official records for the given date range.

    Args:
        from_date: Start of recording date range (inclusive).
        to_date: End of recording date range (inclusive).

    Returns:
        List of record dicts. Empty list on any error.
    """
    session = requests.Session()
    all_records: list[dict] = []

    try:
        viewstate, eventvalidation = _get_viewstate(session)
    except Exception as e:
        logger.error("Broward: failed to load search page — %s", e)
        return []

    for doc_type in _TARGET_DOC_TYPES:
        try:
            # ASP.NET WebForms POST — field names must match the portal's form exactly.
            # Run browser network inspector on official.broward.org/records/search.aspx
            # to confirm the exact input names used by the current form version.
            payload = {
                "__VIEWSTATE": viewstate,
                "__EVENTVALIDATION": eventvalidation,
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "ctl00$MainContent$txtFromDate": from_date.strftime("%m/%d/%Y"),
                "ctl00$MainContent$txtToDate": to_date.strftime("%m/%d/%Y"),
                "ctl00$MainContent$txtDocType": doc_type,
                "ctl00$MainContent$btnSearch": "Search",
            }
            resp = session.post(_SEARCH_URL, data=payload, headers=_HEADERS, timeout=30)
            resp.raise_for_status()

            records = _parse_results(resp.text)
            logger.info("Broward %s: %d records (%s to %s)", doc_type, len(records), from_date, to_date)
            all_records.extend(records)

        except Exception as e:
            logger.error("Broward %s scrape error: %s", doc_type, e)

    return all_records
