import json
import logging
import os
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

_client: Optional[anthropic.Anthropic] = None

SYSTEM_PROMPT = """You are a lead scoring assistant for a real estate investor targeting motivated sellers in South Florida.

Score each distress record from 1 to 10 based on urgency and outreach opportunity:

Scoring criteria:
- Doc type urgency (max 4 points):
  FORECLOSURE or CERTIFICATE OF TITLE = 4 (sale imminent or complete)
  LIS PENDENS = 3 (foreclosure filed, timeline starting)
  PROBATE or PERSONAL REPRESENTATIVE DEED = 3 (estate must liquidate)
  DISSOLUTION OF MARRIAGE = 2 (property division likely)
  DEATH CERTIFICATE = 2 (estate situation developing)
  Other = 1

- Recency (max 3 points):
  Recorded within 7 days = 3
  8-14 days = 2
  15-21 days = 1
  Older = 0

- Contact availability (max 2 points):
  Grantor name clearly present = 1
  Property address present = 1

- Lead quality (max 1 point):
  Property in high-value zip code or clear motivated seller signal = 1

Return ONLY a JSON object with three fields:
- "score": integer 1-10
- "lead_type": one of "Foreclosure", "Probate", "Divorce", "Lis Pendens", "Other"
- "outreach_note": 1-2 sentences on recommended outreach approach (e.g. "LIS PENDENS filed 3 days ago — contact before auction date. Lead with a cash offer and fast close.")
"""


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def score_record(record: dict) -> tuple[int, str, str]:
    """Score a single county record using Claude.

    Args:
        record: Record dict with county, doc_type, recorded_date, grantor, property_address fields.

    Returns:
        Tuple of (score, lead_type, outreach_note).
    """
    user_message = json.dumps({
        "county": record.get("county"),
        "doc_type": record.get("doc_type"),
        "recorded_date": record.get("recorded_date"),
        "grantor": record.get("grantor"),
        "grantee": record.get("grantee"),
        "property_address": record.get("property_address"),
        "property_city": record.get("property_city"),
        "zip_code": record.get("zip_code"),
    })

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        score = int(parsed["score"])
        lead_type = str(parsed["lead_type"])
        outreach_note = str(parsed["outreach_note"])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error("Failed to parse Claude response for %s: %s | raw: %s", record.get("instrument_number"), e, raw)
        score = 1
        lead_type = "Other"
        outreach_note = "Scoring failed — review manually"

    logger.info(
        "Scored %s (%s, %s): %d/10 — %s",
        record.get("instrument_number"),
        record.get("county"),
        record.get("doc_type"),
        score,
        outreach_note[:80],
    )
    return score, lead_type, outreach_note
