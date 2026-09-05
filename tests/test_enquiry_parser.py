"""
Tests for the AI-powered enquiry parser.
"""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.enquiry_parser import parse_enquiry, _rule_based_parse


def test_rule_based_parses_teja():
    """Rule-based parser identifies Teja variety."""
    result = _rule_based_parse(
        "Hi, I am Rajesh from Mumbai. Need 500 kg of Teja chilli. Contact 9876543210."
    )
    assert "Teja" in str(result.get("parsed_variety", ""))
    assert result.get("parsed_quantity") == 500.0


def test_rule_based_parses_quintal():
    """Rule-based parser converts quintals to kg."""
    result = _rule_based_parse("Need 5 quintal Kashmiri chilly powder.")
    assert result.get("parsed_quantity") == 500.0
    assert "Kashmiri" in str(result.get("parsed_variety", ""))


def test_rule_based_parses_byadgi():
    """Rule-based parser identifies Byadgi variety."""
    result = _rule_based_parse("Looking for 100 kg byadagi powder.")
    assert "Byadgi" in str(result.get("parsed_variety", ""))
    assert result.get("parsed_quantity") == 100.0


def test_rule_based_parses_resham():
    """Rule-based parser identifies Resham Patti variety."""
    result = _rule_based_parse("Need 200 kg Resham patti.")
    assert "Resham" in str(result.get("parsed_variety", ""))


def test_rule_based_extracts_phone():
    """Rule-based parser extracts phone numbers."""
    result = _rule_based_parse("Hi, contact me at 9876543210. Need 100 kg Teja.")
    assert "9876543210" in str(result.get("phone", ""))


def test_rule_based_no_match():
    """Rule-based parser returns empty for irrelevant text."""
    result = _rule_based_parse("Hello world!")
    assert result.get("parsed_quantity") is None
    assert result.get("parsed_variety") is None


def test_parse_enquiry_falls_back():
    """parse_enquiry falls back to rule-based when AI is unavailable."""
    with patch("services.enquiry_parser._get_claude_client", return_value=None):
        result = parse_enquiry("I want 50 kg teja powder from Hyderabad.")
    assert result.get("parsed_quantity") == 50.0
    assert "Teja" in str(result.get("parsed_variety", ""))
