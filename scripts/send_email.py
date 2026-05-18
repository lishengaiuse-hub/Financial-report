"""
send_email.py
Sends the generated HTML market report via Gmail SMTP.

Required environment variables (set as GitHub Secrets):
    EMAIL_FROM      — sender Gmail address, e.g. yourname@gmail.com
    EMAIL_PASSWORD  — Gmail App Password (16 chars, NOT login password)
    EMAIL_TO        — recipient(s), comma-separated, e.g. a@gmail.com,b@qq.com

Optional:
    EMAIL_CC        — CC recipients, comma-separated (can be empty)
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

log = logging.getLogger(__name__)


def send(html_path: str, report_date: str = "") -> bool:
    """
    Send the HTML report by email.
    Returns True on success, False if skipped (missing config) or on error.
    """
    email_from = os.environ.get("EMAIL_FROM", "").strip()
    email_pass = os.environ.get("EMAIL_PASSWORD", "").strip()
    email_to   = os.environ.get("EMAIL_TO", "").strip()
    email_cc   = os.environ.get("EMAIL_CC", "").strip()

    # Skip gracefully if any required variable is missing
    if not email_from or not email_pass or not email_to:
        log.info("Email not configured (EMAIL_FROM / EMAIL_PASSWORD / EMAIL_TO missing) — skipping.")
        return False

    if not report_date:
        report_date = datetime.utcnow().strftime("%b %d, %Y")

    # ── Build message ───────────────────────────────────────────────
    msg = MIMEMultipart("mixed")
    msg["From"]    = email_from
    msg["To"]      = email_to
    msg["Subject"] = f"📊 市场情报周报 | Weekly Market Report — {report_date}"
    if email_cc:
        msg["Cc"] = email_cc

    # Read HTML content
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as e:
        log.error(f"Cannot read HTML report: {e}")
        return False

    # ── Part 1: HTML body (inline) ──────────────────────────────────
    # Add a plain-text fallback for clients that don't render HTML
    plain_text = (
        f"市场情报周报 / Weekly Market Report — {report_date}\n\n"
        "此邮件为 HTML 格式，请使用支持 HTML 的邮件客户端查看完整报告。\n"
        "This email is HTML-formatted. Please open with an HTML-capable email client.\n\n"
        f"在线版本 / Online version:\n"
        f"https://lishengaiuse-hub.github.io/Financial-report/"
    )

    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(plain_text, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_content, "html", "utf-8"))
    msg.attach(alt_part)

    # ── Part 2: .html attachment ────────────────────────────────────
    attachment = MIMEBase("application", "octet-stream")
    attachment.set_payload(html_content.encode("utf-8"))
    encoders.encode_base64(attachment)
    safe_date = report_date.replace(",", "").replace(" ", "_")
    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=f"market_report_{safe_date}.html",
    )
    msg.attach(attachment)

    # ── Recipient list ──────────────────────────────────────────────
    to_list = [addr.strip() for addr in email_to.split(",") if addr.strip()]
    cc_list = [addr.strip() for addr in email_cc.split(",") if addr.strip()] if email_cc else []
    all_recipients = to_list + cc_list

    # ── Send via Gmail SMTP ─────────────────────────────────────────
    try:
        log.info(f"Sending report to: {', '.join(all_recipients)}")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(email_from, email_pass)
            server.sendmail(email_from, all_recipients, msg.as_string())
        log.info(f"✅ Email sent successfully to {len(all_recipients)} recipient(s).")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error(
            "Gmail authentication failed. Make sure EMAIL_PASSWORD is a Gmail App Password "
            "(not your login password). Generate at: myaccount.google.com/apppasswords"
        )
    except smtplib.SMTPException as e:
        log.error(f"SMTP error: {e}")
    except Exception as e:
        log.error(f"Email send failed: {e}")

    return False


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    path = sys.argv[1] if len(sys.argv) > 1 else "output/index.html"
    ok = send(path, datetime.utcnow().strftime("%b %d, %Y"))
    sys.exit(0 if ok else 1)
