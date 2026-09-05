"""
Gmail IMAP watcher for IndiaMART enquiry emails.

Polls a Gmail mailbox for new IndiaMART enquiry notifications, parses each
email into a structured lead, and inserts it into the local database.

Why this exists:
    IndiaMART's Pull API is a paid add-on. They do, however, send a free
    email notification to the seller for every new enquiry. This watcher
    reads those emails and converts them into leads automatically.

Configuration (data/secrets.json or env vars):
    {
        "gmail_user": "you@gmail.com",
        "gmail_app_password": "xxxx xxxx xxxx xxxx"
    }

    Or set:
        $env:GMAIL_USER = "you@gmail.com"
        $env:GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"

Generate an app password at:
    https://myaccount.google.com/apppasswords
(requires 2-Step Verification to be enabled on the Google account).
"""

import email
import imaplib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.indiamart_api import load_secrets
from services.enquiry_parser import parse_enquiry
from database.pricing_db import insert_lead, get_all_leads


# State file tracks processed email IDs so we don't double-import.
STATE_FILE = ROOT / "data" / "gmail_watcher_state.json"

# Senders we trust. IndiaMART uses these for enquiry notifications.
INDIAMART_SENDERS = (
    "buyershelpdesk@indiamart.com",
    "buyleads@indiamart.com",
    "buyershelp+enq@indiamart.com",
    "noreply@indiamart.com",
    "leadmanager@indiamart.com",
    "info@indiamart.com",
)

# How many days back to look on the very first run.
INITIAL_LOOKBACK_DAYS = 7

# IMAP server
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


# =========================================================
# STATE MANAGEMENT
# =========================================================

def _load_state() -> dict:
    """Load watcher state (processed IDs, last poll time, last UID)."""
    if not STATE_FILE.exists():
        return {"processed_ids": [], "last_poll": None, "last_uid": "0"}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"processed_ids": [], "last_poll": None, "last_uid": "0"}


def _save_state(state: dict) -> None:
    """Persist watcher state atomically."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


# =========================================================
# CONFIG CHECK
# =========================================================

def is_configured() -> bool:
    """Return True if Gmail credentials are present in secrets/env."""
    secrets = load_secrets()
    return bool(secrets.get("gmail_user") and secrets.get("gmail_app_password"))


# =========================================================
# EMAIL PARSING
# =========================================================

def _decode_header_value(value: str) -> str:
    """Decode a possibly-encoded email header to a plain string."""
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for content, charset in parts:
        if isinstance(content, bytes):
            try:
                decoded.append(content.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded.append(content.decode("utf-8", errors="replace"))
        else:
            decoded.append(content)
    return "".join(decoded)


def _extract_field(text: str, label_patterns: List[str]) -> str:
    """Try a list of label patterns and return the next non-empty value.

    For HTML-stripped text, fields often get glued together ("Anil Phone: 9123...").
    We stop the captured value when we hit a known field label or end-of-string.
    """
    stop_tokens = (
        r"(?:Name|Buyer\s*Name|Phone|Mobile|Mob\.?|Contact|Email|E-?mail|"
        r"City|Location|State|Company|Organization|Subject|Message|Product|"
        r"Quantity|Qty|Requirement|Sender|From)"
    )
    for pat in label_patterns:
        # The value group is captured by the pattern itself. After the match,
        # trim any glued-on trailing content up to the next label.
        m = re.search(pat, text, re.IGNORECASE)
        if not m:
            continue
        raw_val = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else m.group(0).strip()
        # Trim a trailing glued-on field: anything from " <StopToken>:" to end
        trim_re = re.compile(
            r"\s+(?:" + stop_tokens + r")\s*[:\-].*$",
            re.IGNORECASE,
        )
        raw_val = trim_re.sub("", raw_val).strip()
        # Clean up leftover HTML tags if any
        raw_val = re.sub(r"<[^>]+>", "", raw_val).strip()
        if raw_val:
            return raw_val
    return ""


def parse_indiamart_email(msg) -> Dict:
    """
    Parse a parsed email.message.Message into a normalized lead dict.

    Strategy:
        - Subject line: usually "Enquiry for <product> from <name> (<city>)"
        - Body: typically a structured HTML/text block with labeled fields.
    """
    subject = _decode_header_value(msg.get("Subject", ""))
    from_header = _decode_header_value(msg.get("From", ""))
    date_header = msg.get("Date", "")

    body_text = ""
    body_html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp.lower():
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if not payload:
                continue
            try:
                text = payload.decode(part.get_content_charset() or "utf-8",
                                      errors="replace")
            except (LookupError, UnicodeDecodeError):
                text = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain":
                body_text += text
            elif ctype == "text/html":
                body_html += text
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                ctype = msg.get_content_type()
                decoded = payload.decode(
                    msg.get_content_charset() or "utf-8", errors="replace"
                )
                if "html" in ctype:
                    body_html = decoded
                else:
                    body_text = decoded
        except Exception:
            pass

    # Plain text is easier to parse. Fall back to stripped HTML.
    text = body_text
    if not text and body_html:
        text = re.sub(r"<[^>]+>", " ", body_html)
        text = re.sub(r"\s+", " ", text)

    # Field extraction. IndiaMART emails vary in format, so try several
    # label variants for each field.
    customer = _extract_field(text, [
        r"Name\s*[:\-]\s*([^\n\r]+)",
        r"Buyer\s*Name\s*[:\-]\s*([^\n\r]+)",
        r"Sender\s*Name\s*[:\-]\s*([^\n\r]+)",
        r"From\s*[:\-]\s*([^\n\r]+)",
    ])
    phone = _extract_field(text, [
        r"(?:Mobile|Phone|Contact(?:\s*No\.?)?|Mob\.?)\s*[:\-]\s*([+\d\s\-]{8,20})",
    ])
    phone = re.sub(r"[^\d+]", "", phone) if phone else ""

    email_addr = _extract_field(text, [
        r"Email(?:\s*Id)?\s*[:\-]\s*([\w\.\+\-]+@[\w\.\-]+\.\w+)",
    ])
    # If body doesn't yield an email, try the From header
    if not email_addr and "@" in from_header:
        m = re.search(r"[\w\.\+\-]+@[\w\.\-]+\.\w+", from_header)
        if m:
            email_addr = m.group(0)

    location = _extract_field(text, [
        r"City\s*[:\-]\s*([^\n\r]+)",
        r"Location\s*[:\-]\s*([^\n\r]+)",
        r"State\s*[:\-]\s*([^\n\r]+)",
    ]).split(",")[0].strip()

    company = _extract_field(text, [
        r"Company\s*[:\-]\s*([^\n\r]+)",
        r"Organization\s*[:\-]\s*([^\n\r]+)",
    ])

    # Subject often has a better product/variety clue than the body.
    # Examples:
    #   "Enquiry for Chilli Powder from Rajesh (Mumbai)"
    #   "Requirement of Red Chilli Powder - Mumbai"
    product_hint = _extract_field(subject, [
        r"Enquiry for (.+?) from",
        r"Requirement of (.+?)(?:\s*-|\s*$)",
        r"(.+?) enquiry",
    ])

    # Build a "raw text" payload for the AI parser to consume.
    raw_parts = []
    if subject:
        raw_parts.append(f"Subject: {subject}")
    if customer:
        raw_parts.append(f"Name: {customer}")
    if company:
        raw_parts.append(f"Company: {company}")
    if phone:
        raw_parts.append(f"Phone: {phone}")
    if email_addr:
        raw_parts.append(f"Email: {email_addr}")
    if location:
        raw_parts.append(f"City: {location}")
    if product_hint:
        raw_parts.append(f"Product: {product_hint}")
    if text:
        raw_parts.append(f"Message: {text.strip()[:1000]}")
    raw_text = "\n".join(raw_parts)

    received_at = ""
    if date_header:
        try:
            received_at = parsedate_to_datetime(date_header).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except (TypeError, ValueError):
            received_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not received_at:
        received_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "customer": customer,
        "phone": phone,
        "email": email_addr,
        "location": location,
        "company": company,
        "subject": subject,
        "raw_text": raw_text,
        "received_at": received_at,
        "sender_header": from_header,
    }


# =========================================================
# IMAP CONNECTION
# =========================================================

def _connect() -> imaplib.IMAP4_SSL:
    """Open a fresh SSL IMAP connection to Gmail and log in."""
    secrets = load_secrets()
    user = secrets.get("gmail_user")
    pwd = secrets.get("gmail_app_password")
    if not user or not pwd:
        raise RuntimeError(
            "Gmail credentials missing. Add gmail_user and gmail_app_password "
            "to data/secrets.json or set GMAIL_USER / GMAIL_APP_PASSWORD env vars."
        )

    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    conn.login(user, pwd)
    return conn


def _search_since(conn: imaplib.IMAP4_SSL, since_date: str) -> List[bytes]:
    """
    Search INBOX for unseen messages since `since_date` (DD-Mon-YYYY).

    IndiaMART sender filter is applied as a Python-side filter afterwards
    because IMAP OR queries are fiddly across servers.
    """
    typ, data = conn.search(None, f'(UNSEEN SINCE {since_date})')
    if typ != "OK":
        return []
    ids = data[0].split() if data and data[0] else []
    return ids


def _search_initial(conn: imaplib.IMAP4_SSL) -> List[bytes]:
    """On first run, fetch the last N days of unseen mail from any sender."""
    since = (datetime.now() - timedelta(days=INITIAL_LOOKBACK_DAYS))
    since_str = since.strftime("%d-%b-%Y")
    return _search_since(conn, since_str)


def _is_indiamart_sender(from_header: str) -> bool:
    """True if the From: header matches a known IndiaMART sender."""
    f = from_header.lower()
    return any(sender in f for sender in INDIAMART_SENDERS)


# =========================================================
# MAIN POLL
# =========================================================

def poll_once(limit: int = 20) -> Dict:
    """
    Poll Gmail once. Returns a summary dict.

    {
        "fetched": int,        # emails fetched
        "imported": int,       # new leads created
        "skipped": int,        # already processed or non-IndiaMART
        "errors": int,
        "last_poll": str,
    }
    """
    state = _load_state()
    processed = set(state.get("processed_ids", []))

    summary = {
        "fetched": 0,
        "imported": 0,
        "skipped": 0,
        "errors": 0,
        "last_poll": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        conn = _connect()
    except Exception as e:
        summary["errors"] += 1
        summary["error_message"] = str(e)
        return summary

    try:
        conn.select("INBOX")

        # First run vs subsequent runs
        if state.get("last_poll"):
            since = (datetime.now() - timedelta(days=2))
            mail_ids = _search_since(conn, since.strftime("%d-%b-%Y"))
        else:
            mail_ids = _search_initial(conn)

        summary["fetched"] = len(mail_ids)

        for mail_id in mail_ids[-limit:]:
            msg_id = mail_id.decode("utf-8", errors="replace")
            if msg_id in processed:
                summary["skipped"] += 1
                continue

            typ, msg_data = conn.fetch(mail_id, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                summary["errors"] += 1
                continue

            raw = msg_data[0][1]
            try:
                msg = email.message_from_bytes(raw)
            except Exception:
                summary["errors"] += 1
                continue

            from_header = _decode_header_value(msg.get("From", ""))
            if not _is_indiamart_sender(from_header):
                # Not an enquiry email — mark processed so we don't re-check.
                processed.add(msg_id)
                summary["skipped"] += 1
                continue

            try:
                parsed_email = parse_indiamart_email(msg)
            except Exception:
                summary["errors"] += 1
                continue

            try:
                _create_lead_from_email(parsed_email)
                summary["imported"] += 1
            except Exception:
                summary["errors"] += 1

            processed.add(msg_id)

    finally:
        try:
            conn.logout()
        except Exception:
            pass

    # Cap processed_ids list so the state file doesn't grow forever
    processed_list = sorted(processed)
    if len(processed_list) > 5000:
        processed_list = processed_list[-5000:]

    state["processed_ids"] = processed_list
    state["last_poll"] = summary["last_poll"]
    _save_state(state)

    return summary


def _create_lead_from_email(parsed_email: Dict) -> int:
    """Run parsed email through the AI parser and insert as a lead."""
    raw_text = parsed_email.get("raw_text", "")
    ai_parsed = parse_enquiry(raw_text)

    lead = {
        "enquiry_raw_text": raw_text,
        "customer": parsed_email.get("customer")
                  or ai_parsed.get("customer")
                  or "Unknown Customer",
        "phone": parsed_email.get("phone") or ai_parsed.get("phone"),
        "email": parsed_email.get("email") or ai_parsed.get("email"),
        "location": parsed_email.get("location") or ai_parsed.get("location"),
        "company": parsed_email.get("company"),
        "parsed_variety": ai_parsed.get("parsed_variety"),
        "parsed_quantity": ai_parsed.get("parsed_quantity"),
        "source": "gmail_watcher",
        "is_parsed": 1 if (ai_parsed.get("parsed_variety")
                          or ai_parsed.get("parsed_quantity")) else 0,
        "status": "New",
        "created_at": parsed_email.get("received_at")
                      or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # De-dupe: skip if a lead with same phone+variety+qty was inserted
    # in the last 24 hours.
    try:
        recent = get_all_leads()
        for r in recent[:50]:
            if (r.get("phone") and r.get("phone") == lead["phone"]
                    and r.get("parsed_variety") == lead["parsed_variety"]
                    and str(r.get("parsed_quantity")) == str(lead["parsed_quantity"])):
                created = r.get("created_at") or ""
                try:
                    created_dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() - created_dt < timedelta(hours=24):
                        return -1
                except ValueError:
                    pass
    except Exception:
        pass

    return insert_lead(lead)


# =========================================================
# STATUS HELPERS
# =========================================================

def get_status() -> Dict:
    """Return a status dict the UI can display."""
    state = _load_state()
    leads_today = 0
    try:
        for lead in get_all_leads():
            if lead.get("source") == "gmail_watcher" and lead.get("created_at", "").startswith(
                datetime.now().strftime("%Y-%m-%d")
            ):
                leads_today += 1
    except Exception:
        pass

    return {
        "configured": is_configured(),
        "last_poll": state.get("last_poll"),
        "processed_count": len(state.get("processed_ids", [])),
        "leads_today": leads_today,
    }


# =========================================================
# CLI
# =========================================================

def main():
    """CLI entry point: poll once and print summary."""
    if not is_configured():
        print("Gmail credentials not configured. Add gmail_user and "
              "gmail_app_password to data/secrets.json or set env vars.")
        return 1

    print(f"Polling Gmail at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
    summary = poll_once()
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
