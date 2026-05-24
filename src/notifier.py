import logging
import os
import smtplib
from collections import Counter
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _score_color(score: int) -> str:
    if score >= 8:
        return "#C0392B"
    if score >= 6:
        return "#E67E22"
    return "#7F8C8D"


def _score_label(score: int) -> str:
    if score >= 8:
        return "HIGH"
    if score >= 6:
        return "MEDIUM"
    return "LOW"


def _lead_card(record: dict, score: int, lead_type: str, note: str) -> str:
    color = _score_color(score)
    label = _score_label(score)
    address = " ".join(filter(None, [
        record.get("property_address", ""),
        record.get("property_city", ""),
        record.get("zip_code", ""),
    ]))

    def row(label: str, value: str) -> str:
        if not value or value.strip() == "n/a":
            return ""
        return f"""
        <tr>
          <td style="padding:4px 12px 4px 0;color:#7F8C8D;font-size:12px;white-space:nowrap;vertical-align:top;">{label}</td>
          <td style="padding:4px 0;color:#2C3E50;font-size:13px;vertical-align:top;">{value}</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;border:1px solid #E0E0E0;border-radius:6px;overflow:hidden;border-left:4px solid {color};">
      <tr>
        <td style="padding:12px 16px;background:#FAFAFA;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td>
                <span style="font-size:15px;font-weight:600;color:#2C3E50;">{record.get("grantor", "Unknown")}</span>
                &nbsp;
                <span style="font-size:12px;color:#7F8C8D;">{record.get("county")} &middot; {record.get("doc_type")}</span>
              </td>
              <td align="right">
                <span style="background:{color};color:#fff;font-size:11px;font-weight:700;padding:3px 8px;border-radius:4px;letter-spacing:0.5px;">{label} &nbsp;{score}/10</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <tr>
        <td style="padding:12px 16px;">
          <table cellpadding="0" cellspacing="0">
            {row("Address", address)}
            {row("Filed", record.get("recorded_date", ""))}
            {row("Grantee", record.get("grantee", ""))}
            {row("Parcel", record.get("parcel_number", ""))}
            {row("Instrument", record.get("instrument_number", ""))}
            {row("Book / Page", record.get("book_page", ""))}
          </table>
          <div style="margin-top:10px;padding:8px 12px;background:#F4F6F7;border-radius:4px;font-size:12px;color:#555;line-height:1.5;">
            <strong style="color:#2C3E50;">Outreach:</strong> {note}
          </div>
        </td>
      </tr>
    </table>"""


def _build_html(scores: list[tuple[dict, int, str, str]]) -> str:
    run_date = date.today().strftime("%B %d, %Y")
    total = len(scores)
    county_counts = Counter(r.get("county", "Unknown") for r, *_ in scores)
    type_counts = Counter(lt for _, _, lt, _ in scores)
    high = sum(1 for _, s, *_ in scores if s >= 8)
    medium = sum(1 for _, s, *_ in scores if 6 <= s < 8)
    low = sum(1 for _, s, *_ in scores if s < 6)

    sorted_leads = sorted(scores, key=lambda x: x[1], reverse=True)

    county_pills = "".join(
        f'<span style="display:inline-block;margin:2px 4px 2px 0;padding:3px 10px;background:#EBF5FB;color:#2980B9;border-radius:12px;font-size:12px;">{c}: {n}</span>'
        for c, n in sorted(county_counts.items())
    )
    type_pills = "".join(
        f'<span style="display:inline-block;margin:2px 4px 2px 0;padding:3px 10px;background:#F0F0F0;color:#555;border-radius:12px;font-size:12px;">{t}: {n}</span>'
        for t, n in sorted(type_counts.items())
    )

    lead_cards = "".join(_lead_card(r, s, lt, note) for r, s, lt, note in sorted_leads)

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F2F3F4;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F2F3F4;padding:24px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="background:#1A252F;padding:24px 28px;border-radius:6px 6px 0 0;">
              <div style="color:#fff;font-size:18px;font-weight:700;letter-spacing:0.3px;">County Records Lead Monitor</div>
              <div style="color:#95A5A6;font-size:12px;margin-top:4px;">Week of {run_date} &middot; {total} new lead{"s" if total != 1 else ""}</div>
            </td>
          </tr>

          <!-- Summary stats -->
          <tr>
            <td style="background:#fff;padding:16px 28px;border-bottom:1px solid #E8E8E8;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="padding:8px;border-right:1px solid #E8E8E8;">
                    <div style="font-size:26px;font-weight:700;color:#C0392B;">{high}</div>
                    <div style="font-size:11px;color:#7F8C8D;letter-spacing:0.5px;">HIGH</div>
                  </td>
                  <td align="center" style="padding:8px;border-right:1px solid #E8E8E8;">
                    <div style="font-size:26px;font-weight:700;color:#E67E22;">{medium}</div>
                    <div style="font-size:11px;color:#7F8C8D;letter-spacing:0.5px;">MEDIUM</div>
                  </td>
                  <td align="center" style="padding:8px;">
                    <div style="font-size:26px;font-weight:700;color:#7F8C8D;">{low}</div>
                    <div style="font-size:11px;color:#7F8C8D;letter-spacing:0.5px;">LOW</div>
                  </td>
                </tr>
              </table>
              <div style="margin-top:12px;">{county_pills}</div>
              <div style="margin-top:6px;">{type_pills}</div>
            </td>
          </tr>

          <!-- Lead cards -->
          <tr>
            <td style="background:#fff;padding:20px 28px;border-radius:0 0 6px 6px;">
              <div style="font-size:13px;font-weight:700;color:#7F8C8D;letter-spacing:0.8px;margin-bottom:14px;text-transform:uppercase;">All Leads — Sorted by Urgency</div>
              {lead_cards}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:16px 0;text-align:center;">
              <div style="font-size:11px;color:#AAB7B8;">County Records Monitor &middot; Automated weekly digest</div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_weekly_digest(scores: list[tuple[dict, int, str, str]]) -> None:
    """Send a weekly digest email with all new leads found this run.

    Args:
        scores: List of (record, score, lead_type, outreach_note) tuples.
    """
    smtp_user = os.environ.get("GMAIL_USER", "")
    smtp_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    alert_email = os.environ.get("ALERT_EMAIL", smtp_user)

    if not smtp_user or not smtp_password:
        logger.warning("GMAIL_USER or GMAIL_APP_PASSWORD not set — skipping email digest")
        return

    if not scores:
        logger.info("No new leads this run — skipping email digest")
        return

    total = len(scores)
    html = _build_html(scores)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"County Records Monitor: {total} new lead{'s' if total != 1 else ''} this week"
    msg["From"] = smtp_user
    msg["To"] = alert_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, alert_email, msg.as_string())
        logger.info("Weekly digest sent to %s (%d leads)", alert_email, total)
    except Exception as e:
        logger.error("Failed to send digest email: %s", e)
