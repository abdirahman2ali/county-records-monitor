import logging
from datetime import date

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Miami-Dade Clerk of Courts Official Records
# Portal: https://www2.miami-dadeclerk.com/officialrecords/
_BASE_URL = "https://www2.miami-dadeclerk.com"
_SEARCH_URL = f"{_BASE_URL}/officialrecords/StandardSearch.aspx"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": f"{_BASE_URL}/officialrecords/",
}

# Miami-Dade uses numeric doc type codes — verify current codes in the portal dropdown
# Common codes: LP = Lis Pendens, FC = Foreclosure, etc.
_TARGET_DOC_TYPE_CODES = {
    "LIS PENDENS": "LPEN",
    "FORECLOSURE": "FREC",
    "PROBATE": "PROB",
    "DEATH CERTIFICATE": "DEAT",
    "DISSOLUTION OF MARRIAGE": "DISS",
    "PERSONAL REPRESENTATIVE DEED": "PRDE",
    "CERTIFICATE OF TITLE": "CTIT",
}


def _get_viewstate(session: requests.Session) -> tuple[str, str]:
    """Fetch search page and extract ASP.NET ViewState tokens."""
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
    """Parse Miami-Dade results page into record dicts."""
    soup = BeautifulSoup(html, "html.parser")
    records = []

    table = soup.find("table", {"id": lambda x: x and "grid" in (x or "").lower()})
    if table is None:
        table = soup.find("table", id=lambda x: x and "result" in (x or "").lower())

    if table is None:
        logger.debug("No results table found in Miami-Dade response")
        return records

    rows = table.find_all("tr")
    headers = [th.get_text(strip=True).upper() for th in rows[0].find_all(["th", "td"])] if rows else []

    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cells or len(cells) < 3:
            continue

        def cell(name: str, pos: int) -> str:
            try:
                idx = next(i for i, h in enumerate(headers) if name in h)
                return cells[idx] if idx < len(cells) else ""
            except StopIteration:
                return cells[pos] if pos < len(cells) else ""

        records.append({
            "county": "Miami-Dade",
            "instrument_number": cell("CFN", 0),
            "doc_type": cell("DOC", 1).upper(),
            "recorded_date": cell("RECORDED", 2),
            "grantor": cell("GRANTOR", 3),
            "grantee": cell("GRANTEE", 4),
            "property_address": cell("ADDRESS", 5),
            "property_city": cell("CITY", 6),
            "zip_code": cell("ZIP", 7),
            "parcel_number": cell("FOLIO", 8),
            "book_page": cell("BOOK", 9),
        })

    return records


def fetch_new_records(from_date: date, to_date: date) -> list[dict]:
    """Fetch Miami-Dade County official records for the given date range.

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
        logger.error("Miami-Dade: failed to load search page — %s", e)
        return []

    for doc_label, doc_code in _TARGET_DOC_TYPE_CODES.items():
        try:
            # Miami-Dade form fields — verify against the current portal version.
            # Inspect via browser dev tools on www2.miami-dadeclerk.com/officialrecords/
            payload = {
                "__VIEWSTATE": viewstate,
                "__EVENTVALIDATION": eventvalidation,
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "ctl00$cphPage$SearchControl1$txtFromDate": from_date.strftime("%m/%d/%Y"),
                "ctl00$cphPage$SearchControl1$txtToDate": to_date.strftime("%m/%d/%Y"),
                "ctl00$cphPage$SearchControl1$ddlDocType": doc_code,
                "ctl00$cphPage$SearchControl1$btnSearch": "Search",
            }
            resp = session.post(_SEARCH_URL, data=payload, headers=_HEADERS, timeout=30)
            resp.raise_for_status()

            records = _parse_results(resp.text)
            logger.info("Miami-Dade %s: %d records (%s to %s)", doc_label, len(records), from_date, to_date)
            all_records.extend(records)

        except Exception as e:
            logger.error("Miami-Dade %s scrape error: %s", doc_label, e)

    return all_records
