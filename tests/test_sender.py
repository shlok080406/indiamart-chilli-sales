"""
Tests for email and WhatsApp senders (with mocks).
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_email_sender_not_configured():
    """Email sender returns failure when not configured."""
    from services.email_sender import send_email, is_email_configured

    with patch("services.email_sender.is_email_configured", return_value=False):
        result = send_email("test@example.com", "Subject", "Body", b"pdf-bytes")
        assert result["success"] is False
        assert "not configured" in result["error"]


def test_quotation_sender_orchestrates_email():
    """quotation_sender delegates to email_sender when channel=email."""
    from services.quotation_sender import send_quotation

    lead = {
        "id": 1,
        "customer": "Test Customer",
        "email": "test@example.com",
        "phone": "9876543210",
    }

    with patch("services.quotation_sender.is_email_configured", return_value=True), \
         patch("services.quotation_sender.is_whatsapp_configured", return_value=False), \
         patch("services.quotation_sender.send_email", return_value={"success": True}), \
         patch("services.quotation_sender.save_quotation"):
        result = send_quotation(
            lead=lead,
            product_name="Teja / Guntur",
            quantity=500,
            rate_per_kg=150.0,
            pdf_bytes=b"fake-pdf",
            channel="email",
        )

    assert result["success"] is True
    assert "email" in result["channel"]


def test_quotation_sender_handles_no_channel():
    """quotation_sender returns failure when channel is unavailable."""
    from services.quotation_sender import send_quotation

    lead = {
        "id": 1,
        "customer": "Test Customer",
        "phone": None,
        "email": None,
    }

    with patch("services.quotation_sender.is_email_configured", return_value=False), \
         patch("services.quotation_sender.is_whatsapp_configured", return_value=False):
        result = send_quotation(
            lead=lead,
            product_name="Teja / Guntur",
            quantity=500,
            rate_per_kg=150.0,
            pdf_bytes=b"fake-pdf",
            channel="email",
        )

    assert result["success"] is False


def test_email_send_calls_smtp():
    """Email send actually attempts SMTP connection when configured."""
    from services.email_sender import send_email

    mock_server = MagicMock()
    mock_smtp = MagicMock()
    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

    secrets = {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "user@gmail.com",
        "smtp_password": "password",
        "smtp_from_email": "user@gmail.com",
    }

    with patch("services.email_sender.load_email_secrets", return_value=secrets), \
         patch("services.email_sender.smtplib.SMTP", mock_smtp):
        result = send_email("recipient@example.com", "Test Subject", "Body", b"pdf")

    assert result["success"] is True
    assert mock_server.sendmail.called
