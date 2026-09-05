"""Tests for the Gmail IMAP watcher.

These tests focus on the parser and dedupe logic. IMAP connection is mocked.
"""
import sys
import email
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.gmail_watcher import (
    parse_indiamart_email,
    _extract_field,
    _is_indiamart_sender,
    _decode_header_value,
    poll_once,
    is_configured,
)


def _build_email(from_addr, subject, body, date="Mon, 01 Sep 2026 10:00:00 +0530"):
    """Build a raw RFC822 email.message.Message for testing."""
    raw = (
        f"From: {from_addr}\r\n"
        f"To: you@gmail.com\r\n"
        f"Subject: {subject}\r\n"
        f"Date: {date}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"{body}\r\n"
    )
    return email.message_from_string(raw)


def test_extract_field_basic():
    text = "Name: Rajesh Kumar\nPhone: 9876543210\nCity: Mumbai"
    assert _extract_field(text, [r"Name\s*[:\-]\s*([^\n\r]+)"]) == "Rajesh Kumar"
    assert _extract_field(text, [r"Phone\s*[:\-]\s*([+\d\s\-]+)"]) == "9876543210"
    assert _extract_field(text, [r"City\s*[:\-]\s*([^\n\r]+)"]) == "Mumbai"
    assert _extract_field(text, [r"Nonexistent\s*[:\-]\s*(.+)"]) == ""


def test_extract_field_multiple_patterns():
    text = "Buyer Name: Priya"
    # First pattern fails, second succeeds
    val = _extract_field(text, [
        r"Name\s*[:\-]\s*([^\n\r]+)",
        r"Buyer Name\s*[:\-]\s*([^\n\r]+)",
    ])
    assert val == "Priya"


def test_is_indiamart_sender_known_addresses():
    assert _is_indiamart_sender("buyershelpdesk@indiamart.com")
    assert _is_indiamart_sender("IndiaMART <buyleads@indiamart.com>")
    assert _is_indiamart_sender("noreply@indiamart.com")
    assert not _is_indiamart_sender("someone@gmail.com")
    assert not _is_indiamart_sender("")


def test_decode_header_value_plain():
    assert _decode_header_value("Hello") == "Hello"


def test_parse_indiamart_email_full_body():
    body = (
        "Name: Rajesh Kumar\n"
        "Company: Spice Traders\n"
        "Mobile: +91 98765 43210\n"
        "Email: rajesh@spicetraders.com\n"
        "City: Mumbai\n"
        "Message: I need 500 kg of Teja chilli powder for export."
    )
    msg = _build_email(
        "buyershelpdesk@indiamart.com",
        "Enquiry for Chilli Powder from Rajesh",
        body,
    )

    parsed = parse_indiamart_email(msg)

    assert parsed["customer"] == "Rajesh Kumar"
    assert parsed["company"] == "Spice Traders"
    assert parsed["phone"] == "+919876543210" or parsed["phone"] == "919876543210"
    assert parsed["email"] == "rajesh@spicetraders.com"
    assert parsed["location"] == "Mumbai"
    assert "Subject:" in parsed["raw_text"]
    assert "Rajesh Kumar" in parsed["raw_text"]
    assert parsed["received_at"].startswith("2026-09-01")


def test_parse_indiamart_email_minimal():
    msg = _build_email(
        "buyleads@indiamart.com",
        "Requirement of Red Chilli Powder - Delhi",
        "Please share best price for 1 ton.",
    )
    parsed = parse_indiamart_email(msg)
    assert parsed["customer"] == ""
    assert parsed["raw_text"]
    assert "Red Chilli Powder" in parsed["raw_text"] or "red chilli" in parsed["raw_text"].lower()


def test_parse_indiamart_email_html_only():
    raw = (
        "From: noreply@indiamart.com\r\n"
        "Subject: New Lead\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "\r\n"
        "<html><body>"
        "<p>Name: Anil</p><p>Phone: 9123456789</p><p>City: Pune</p>"
        "<p>Message: Want 100 kg Teja S17.</p>"
        "</body></html>\r\n"
    )
    msg = email.message_from_string(raw)
    parsed = parse_indiamart_email(msg)
    assert parsed["customer"] == "Anil"
    assert "9123456789" in parsed["phone"]
    assert parsed["location"] == "Pune"


def test_is_configured_with_env(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "you@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    assert is_configured() is True


def test_is_configured_missing(monkeypatch):
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    assert is_configured() is False


def test_poll_once_handles_connection_error(monkeypatch):
    """If IMAP login fails, poll_once should return a clean error summary
    rather than crash."""
    monkeypatch.setenv("GMAIL_USER", "you@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")

    with patch("services.gmail_watcher._connect",
               side_effect=RuntimeError("auth failed")):
        summary = poll_once()
    assert summary["errors"] >= 1
    assert "auth failed" in summary.get("error_message", "")


def test_poll_once_imports_new_email(monkeypatch, tmp_path):
    """Mock the full IMAP round trip and assert a lead is created."""
    monkeypatch.setenv("GMAIL_USER", "you@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")

    # Use a fresh state file for this test
    state_file = tmp_path / "state.json"
    monkeypatch.setattr("services.gmail_watcher.STATE_FILE", state_file)

    body = "Name: Ramesh\nPhone: 9988776655\nCity: Guntur\nMessage: Need 200 kg Teja."
    raw_email = (
        "From: buyershelpdesk@indiamart.com\r\n"
        "Subject: New enquiry\r\n"
        "Date: Mon, 01 Sep 2026 10:00:00 +0530\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{body}\r\n"
    )

    mock_conn = MagicMock()
    mock_conn.search.return_value = ("OK", [b"1"])
    mock_conn.select.return_value = ("OK", [b"1"])
    mock_conn.fetch.return_value = ("OK", [(b"1 (RFC822 {N}", raw_email.encode())])
    mock_conn.logout.return_value = ("OK", [None])

    with patch("services.gmail_watcher._connect", return_value=mock_conn), \
         patch("services.gmail_watcher.insert_lead", return_value=42) as mock_insert, \
         patch("services.gmail_watcher.get_all_leads", return_value=[]):
        summary = poll_once()

    assert summary["fetched"] == 1
    assert summary["imported"] == 1
    assert mock_insert.called
    lead_arg = mock_insert.call_args[0][0]
    assert lead_arg["customer"] == "Ramesh"
    assert lead_arg["source"] == "gmail_watcher"
    assert lead_arg["status"] == "New"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
