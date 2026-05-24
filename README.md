# County Records Lead Monitor

Monitors Broward, Miami-Dade, and Palm Beach County official records weekly for distress-related filings. Relevant records (foreclosures, lis pendens, probate, death, divorce) are scored by urgency using Claude AI and emailed as a digest.

## Architecture

```
GitHub Actions (weekly, Monday 8 AM UTC)
    └── main.py
            ├── County scrapers (Broward, Miami-Dade, Palm Beach)
            ├── Distress keyword filter
            ├── Dedup store (Neon Postgres)
            ├── Claude AI scorer (urgency 1–10 + outreach note)
            └── Email digest (all leads sorted by score)
```

## Scraper Notes

The county portal scrapers use publicly available search interfaces. If a scraper returns 0 results, verify the form field names against the live portal using your browser's network inspector — county portals occasionally update their ASP.NET form parameters.
