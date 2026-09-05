"""
Long-running background watcher for the Gmail enquiry importer.

Polls Gmail on a fixed schedule (default: every 5 minutes) and imports new
IndiaMART enquiry emails as leads.

Usage:
    py run_watcher.py                    # poll every 5 minutes
    py run_watcher.py --interval 60      # poll every 60 seconds
    py run_watcher.py --once             # poll once and exit (for cron)

Logs are written to data/gmail_watcher.log.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.gmail_watcher import is_configured, poll_once, get_status


LOG_FILE = ROOT / "data" / "gmail_watcher.log"


def _setup_logging() -> None:
    """Configure a simple rotating log file + console output."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_once() -> int:
    """Run a single poll cycle. Returns process exit code."""
    if not is_configured():
        logging.error(
            "Gmail not configured. Add gmail_user and gmail_app_password "
            "to data/secrets.json or set GMAIL_USER / GMAIL_APP_PASSWORD."
        )
        return 1

    summary = poll_once()
    logging.info(f"Poll complete: {summary}")
    return 0 if summary.get("errors", 0) == 0 else 1


def run_scheduler(interval_seconds: int) -> int:
    """Start APScheduler and run poll_once on a fixed interval."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        logging.error(
            "apscheduler not installed. Run: pip install apscheduler>=3.10.0"
        )
        return 1

    if not is_configured():
        logging.error("Gmail not configured. Exiting.")
        return 1

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        run_once,
        "interval",
        seconds=interval_seconds,
        id="gmail_poll",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )

    logging.info(
        f"Gmail watcher started. Polling every {interval_seconds} seconds."
    )
    logging.info(f"Status: {get_status()}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Watcher stopped by user.")
        scheduler.shutdown()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Background Gmail IMAP watcher for IndiaMART enquiries."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Polling interval in seconds (default: 300 = 5 minutes).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single poll and exit. Useful for cron jobs.",
    )
    args = parser.parse_args()

    _setup_logging()

    if args.once:
        return run_once()
    return run_scheduler(args.interval)


if __name__ == "__main__":
    sys.exit(main())
