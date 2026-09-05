"""
Tests for the follow-up scheduling service.
"""

import sys
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.followup_scheduler import (
    calculate_next_follow_up,
    get_overdue_leads,
    get_due_today_leads,
    get_upcoming_leads,
    get_follow_up_days,
)


MOCK_RULES = {
    "follow_up_after_days": {
        "New": 1,
        "Follow-up": 7,
        "Quoted": 3,
        "Converted": 0,
        "Lost": 0,
    }
}


def test_get_follow_up_days_new():
    """New leads follow up in 1 day."""
    with patch("services.followup_scheduler.load_business_rules", return_value=MOCK_RULES):
        days = get_follow_up_days("New")
        assert days == 1


def test_get_follow_up_days_quoted():
    """Quoted leads follow up in 3 days."""
    with patch("services.followup_scheduler.load_business_rules", return_value=MOCK_RULES):
        days = get_follow_up_days("Quoted")
        assert days == 3


def test_calculate_next_follow_up_default():
    """Without args, calculates from today."""
    with patch("services.followup_scheduler.load_business_rules", return_value=MOCK_RULES):
        result = calculate_next_follow_up("New")
    today = datetime.now()
    expected = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    assert result == expected


def test_calculate_next_follow_up_from_date():
    """With from_date arg, calculates from that date."""
    with patch("services.followup_scheduler.load_business_rules", return_value=MOCK_RULES):
        from_date = datetime(2026, 9, 1)
        result = calculate_next_follow_up("Quoted", from_date=from_date)
    assert result == "2026-09-04"


def test_get_overdue_leads():
    """get_overdue_leads returns leads with next_follow_up < today."""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    leads = [
        {"id": 1, "next_follow_up": yesterday, "customer": "Overdue"},
        {"id": 2, "next_follow_up": today, "customer": "Today"},
        {"id": 3, "next_follow_up": None, "customer": "No follow-up"},
    ]

    overdue = get_overdue_leads(leads)
    assert len(overdue) == 1
    assert overdue[0]["customer"] == "Overdue"


def test_get_due_today_leads():
    """get_due_today_leads returns leads with next_follow_up == today."""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    leads = [
        {"id": 1, "next_follow_up": yesterday, "customer": "Overdue"},
        {"id": 2, "next_follow_up": today, "customer": "Today"},
    ]

    due_today = get_due_today_leads(leads)
    assert len(due_today) == 1
    assert due_today[0]["customer"] == "Today"


def test_get_upcoming_leads():
    """get_upcoming_leads returns leads in the next 7 days, excluding today."""
    today = datetime.now()
    in_3_days = (today + timedelta(days=3)).strftime("%Y-%m-%d")
    in_8_days = (today + timedelta(days=8)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    leads = [
        {"id": 1, "next_follow_up": today_str, "customer": "Today"},
        {"id": 2, "next_follow_up": in_3_days, "customer": "Soon"},
        {"id": 3, "next_follow_up": in_8_days, "customer": "Far"},
    ]

    upcoming = get_upcoming_leads(leads, days=7)
    assert len(upcoming) == 1
    assert upcoming[0]["customer"] == "Soon"
