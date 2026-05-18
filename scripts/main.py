"""
main.py — Entrypoint for the weekly market report pipeline.
Usage:
    python scripts/main.py

Steps:
  1. Fetch all market data (US + China A-share)
  2. Generate HTML report
  3. Send email (if EMAIL_FROM / EMAIL_PASSWORD / EMAIL_TO are set)
"""
import os, sys, json, logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(root, "output")
    os.makedirs(output_dir, exist_ok=True)

    # ── Step 1: Fetch data ──────────────────────────────────────────
    log.info("═══ Step 1/3: Fetching market data ═══")
    from fetch_data import run as fetch_run
    data = fetch_run()

    data_path = os.path.join(output_dir, "data.json")
    with open(data_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    log.info(f"Data saved → {data_path}")

    # ── Step 2: Generate HTML report ────────────────────────────────
    log.info("═══ Step 2/3: Generating HTML report ═══")
    from generate_report import generate
    html = generate(data)

    html_path = os.path.join(output_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"Report saved → {html_path}")

    # ── Step 3: Send email ──────────────────────────────────────────
    log.info("═══ Step 3/3: Sending email ═══")
    from send_email import send
    send(html_path, report_date=data.get("report_date", ""))

    log.info("✅ Done.")

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
