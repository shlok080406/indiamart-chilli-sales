"""
Follow-up scheduling service.

Automatically calculates the next follow-up date based on lead status
and business rules stored in business_rules.json.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent.parent
BUSINESS_RULES_FILE = ROOT / "data" / "business_rules.json"


def load_business_rules() -> dict:
    """Load business rules from JSON."""
    try:
        with open(BUSINESS_RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_follow_up_days(status: str) -> int:
    """Return the number of days until the next follow-up for a given status."""
    rules = load_business_rules()
    follow_up_rules = rules.get("follow_up_after_days", {})
    return follow_up_rules.get(status, 3)  # default: 3 days


def calculate_next_follow_up(status: str, from_date: datetime = None) -> str:
    """
    Return the next follow-up date as a string (YYYY-MM-DD) based on status.

    Example: New leads → follow up in 1 day
             Quoted leads → follow up in 3 days
             Follow-up leads → follow up in 7 days
    """
    if from_date is None:
        from_date = datetime.now()

    days = get_follow_up_days(status)
    follow_up_date = from_date + timedelta(days=days)

    return follow_up_date.strftime("%Y-%m-%d")


def get_overdue_leads(leads: list) -> list:
    """Filter leads that are overdue for follow-up (next_follow_up < today)."""
    today = datetime.now().strftime("%Y-%m-%d")
    overdue = []

    for lead in leads:
        next_follow_up = lead.get("next_follow_up")
        if next_follow_up and next_follow_up < today:
            overdue.append(lead)

    return overdue


def get_due_today_leads(leads: list) -> list:
    """Filter leads whose follow-up is due today."""
    today = datetime.now().strftime("%Y-%m-%d")
    return [lead for lead in leads if lead.get("next_follow_up") == today]


def get_upcoming_leads(leads: list, days: int = 7) -> list:
    """Filter leads with follow-ups within the next N days (not including today)."""
    today = datetime.now().date()
    cutoff = today + timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    upcoming = []
    for lead in leads:
        next_follow_up = lead.get("next_follow_up")
        if next_follow_up and today_str < next_follow_up <= cutoff_str:
            upcoming.append(lead)

    return upcoming
