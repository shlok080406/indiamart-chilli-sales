"""
Email sender service using SMTP.

Sends a PDF quotation via email using SMTP credentials from secrets.json.
"""

import smtplib
import ssl
import json
import os
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders


ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = ROOT / "data" / "secrets.json"


def load_email_secrets() -> dict:
    """Load SMTP credentials from secrets.json or environment variables."""
    secrets = {}

    if SECRETS_FILE.exists():
        try:
            with open(SECRETS_FILE, "r", encoding="utf-8") as f:
                secrets = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Environment overrides
    env_keys = [
        "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from_email", "smtp_from_name"
    ]
    for key in env_keys:
        val = os.environ.get(f"EMAIL_{key.upper()}")
        if val:
            secrets[key] = val

    return secrets


def is_email_configured() -> bool:
    secrets = load_email_secrets()
    return bool(
        secrets.get("smtp_host")
        and secrets.get("smtp_user")
        and secrets.get("smtp_password")
    )


def send_email(
    to_email: str,
    subject: str,
    body_text: str,
    pdf_bytes: bytes,
    filename: str = "quotation.pdf",
) -> dict:
    """
    Send a quotation email with a PDF attachment.

    Returns {"success": True} or {"success": False, "error": "..."}.
    """
    secrets = load_email_secrets()

    if not is_email_configured():
        return {"success": False, "error": "Email not configured."}

    host = secrets["smtp_host"]
    port = int(secrets.get("smtp_port", 587))
    user = secrets["smtp_user"]
    password = secrets["smtp_password"]
    from_email = secrets.get("smtp_from_email", user)
    from_name = secrets.get("smtp_from_name", "Vijaylaxmi Trading Company")

    msg = MIMEMultipart()
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    # Plain text body
    msg.attach(MIMEText(body_text, "plain"))

    # PDF attachment
    part = MIMEBase("application", "octet-stream")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={filename}")
    msg.attach(part)

    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context) as server:
                server.login(user, password)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                server.ehlo()
                server.starttls()
                server.login(user, password)
                server.sendmail(from_email, [to_email], msg.as_string())

        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}


def build_quotation_email_body(customer_name: str, product: str, quantity: float, total: float) -> str:
    """Build the email body for a quotation."""
    return f"""Dear {customer_name},

Thank you for your enquiry. Please find attached our quotation for your reference.

Product: {product}
Quantity: {quantity:,.0f} kg
Total Value: Rs. {total:,.2f}

This quotation is valid for 7 days. Please feel free to reach out for any clarifications.

Best regards,
Vijaylaxmi Trading Company
Phone: 9740218812
"""
