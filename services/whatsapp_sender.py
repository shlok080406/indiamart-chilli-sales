"""
WhatsApp sender service.

Uses the WhatsApp Business Cloud API (Meta) to send a quotation as a document.

Prerequisites:
- WhatsApp Business account
- Meta app with WhatsApp product enabled
- Phone number ID
- Permanent access token
"""

import json
import os
import requests
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = ROOT / "data" / "secrets.json"


def load_whatsapp_secrets() -> dict:
    """Load WhatsApp credentials from secrets.json or environment variables."""
    secrets = {}

    if SECRETS_FILE.exists():
        try:
            with open(SECRETS_FILE, "r", encoding="utf-8") as f:
                secrets = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    env_keys = ["whatsapp_token", "whatsapp_phone_id"]
    for key in env_keys:
        val = os.environ.get(f"WHATSAPP_{key.upper()}")
        if val:
            secrets[key] = val

    return secrets


def is_whatsapp_configured() -> bool:
    secrets = load_whatsapp_secrets()
    return bool(secrets.get("whatsapp_token") and secrets.get("whatsapp_phone_id"))


def send_quotation_whatsapp(
    to_phone: str,
    customer_name: str,
    product: str,
    quantity: float,
    total: float,
    pdf_bytes: bytes,
    filename: str = "quotation.pdf",
) -> dict:
    """
    Send a quotation via WhatsApp Cloud API.

    Returns {"success": True, "message_id": "..."} or
            {"success": False, "error": "..."}.
    """
    if not is_whatsapp_configured():
        return {"success": False, "error": "WhatsApp not configured."}

    secrets = load_whatsapp_secrets()
    token = secrets["whatsapp_token"]
    phone_id = secrets["whatsapp_phone_id"]

    # Normalize phone to international format
    to_phone = to_phone.strip().replace(" ", "").replace("-", "")
    if not to_phone.startswith("+"):
        to_phone = "+91" + to_phone  # default to India

    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # First, upload the PDF to get a media_id
    upload_url = f"https://graph.facebook.com/v18.0/{phone_id}/media"
    files = {
        "file": (filename, pdf_bytes, "application/pdf"),
    }
    upload_data = {
        "messaging_product": "whatsapp",
        "type": "application/pdf",
    }
    upload_params = {"access_token": token}

    try:
        upload_response = requests.post(
            upload_url, files=files, data=upload_data, params=upload_params, timeout=30
        )
        upload_response.raise_for_status()
        media_id = upload_response.json().get("id")
    except (requests.RequestException, KeyError) as e:
        return {"success": False, "error": f"Upload failed: {e}"}

    if not media_id:
        return {"success": False, "error": "Failed to upload PDF to WhatsApp."}

    # Send a text message + the document
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone.lstrip("+"),
        "type": "template",
        "template": {
            "name": "quotation_document",
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": customer_name},
                        {"type": "text", "text": product},
                        {"type": "text", "text": f"{quantity:,.0f} kg"},
                        {"type": "text", "text": f"Rs. {total:,.2f}"},
                    ],
                },
                {
                    "type": "header",
                    "parameters": [
                        {"type": "document", "document": {"id": media_id, "filename": filename}}
                    ],
                },
            ],
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        message_id = data.get("messages", [{}])[0].get("id", "")
        return {"success": True, "message_id": message_id}
    except (requests.RequestException, KeyError) as e:
        return {"success": False, "error": str(e)}
