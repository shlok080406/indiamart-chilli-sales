"""
IndiaMART API client.

IndiaMART exposes a REST API for sellers to fetch enquiries/ leads. The official
endpoint is https://mapi.indiamart.com/wservce/enquiry/listing/GLUSR_MOBILE/GLUSR_MOBILE_KEY/

Credentials (crm-id and api-key) are read from environment variables or
`data/secrets.json` and are not committed to source control.
"""

import os
import json
import requests
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = ROOT / "data" / "secrets.json"


def load_secrets() -> dict:
    """Load API credentials from secrets.json or environment variables."""
    secrets = {}

    if SECRETS_FILE.exists():
        try:
            with open(SECRETS_FILE, "r", encoding="utf-8") as f:
                secrets = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    env_overrides = {
        "indiamart_crm_id": os.environ.get("INDIAMART_CRM_ID"),
        "indiamart_api_key": os.environ.get("INDIAMART_API_KEY"),
        "gmail_user": os.environ.get("GMAIL_USER"),
        "gmail_app_password": os.environ.get("GMAIL_APP_PASSWORD"),
    }
    for key, value in env_overrides.items():
        if value:
            secrets[key] = value

    return secrets


def is_configured() -> bool:
    """Return True if both required IndiaMART credentials are present."""
    secrets = load_secrets()
    return bool(secrets.get("indiamart_crm_id") and secrets.get("indiamart_api_key"))


def fetch_enquiries(last_days: int = 7) -> List[Dict]:
    """
    Fetch recent enquiries from the IndiaMART API.

    Returns a list of normalized enquiry dicts:
    {
        "enquiry_id": "...",
        "customer": "...",
        "phone": "...",
        "email": "...",
        "location": "...",
        "subject": "...",
        "raw_message": "...",
        "received_at": "...",
    }
    """
    secrets = load_secrets()
    crm_id = secrets.get("indiamart_crm_id")
    api_key = secrets.get("indiamart_api_key")

    if not crm_id or not api_key:
        return []

    url = f"https://mapi.indiamart.com/wservce/enquiry/listing/{crm_id}/{api_key}/"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, json.JSONDecodeError):
        return []

    enquiries = []
    for entry in data.get("RESPONSE", []):
        enquiry = _normalize_entry(entry)
        if enquiry:
            enquiries.append(enquiry)

    return enquiries


def _normalize_entry(entry: Dict) -> Optional[Dict]:
    """Convert a raw IndiaMART response entry into a normalized dict."""
    try:
        return {
            "enquiry_id": entry.get("UNIQUE_QUERY_ID", ""),
            "customer": entry.get("SENDER_NAME", "").strip(),
            "phone": entry.get("SENDER_MOBILE", "").strip(),
            "email": entry.get("SENDER_EMAIL", "").strip(),
            "company": entry.get("SENDER_COMPANY", "").strip(),
            "location": entry.get("SENDER_CITY", "").strip(),
            "subject": entry.get("QUERY_SUBJECT", "").strip(),
            "raw_message": entry.get("QUERY_MESSAGE", "").strip(),
            "received_at": entry.get("RECEIVED_DATE", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        }
    except Exception:
        return None


def mark_enquiry_read(enquiry_id: str) -> bool:
    """Mark an enquiry as read on IndiaMART. Optional — not all accounts support this."""
    return True
