"""
Quotation sender orchestrator.

Picks the best delivery channel (email first, WhatsApp fallback) and sends
the PDF quotation to the customer, logging it in the database.
"""

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.pricing_db import save_quotation
from services.email_sender import (
    send_email,
    build_quotation_email_body,
    is_email_configured,
)
from services.whatsapp_sender import (
    send_quotation_whatsapp,
    is_whatsapp_configured,
)


def send_quotation(
    lead: dict,
    product_name: str,
    quantity: float,
    rate_per_kg: float,
    pdf_bytes: bytes,
    channel: str = "email",
) -> dict:
    """
    Orchestrate sending a quotation via the chosen channel.

    Channels: "email", "whatsapp", or "both"

    Returns {"success": bool, "channel": str, "error": str or None}
    """
    total = quantity * rate_per_kg
    customer = lead.get("customer", "Customer")
    email = lead.get("email", "")
    phone = lead.get("phone", "")
    quotation_no = f"QTN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    safe_customer = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "_"
        for c in customer
    ).strip().replace(" ", "_")

    filename = f"Quotation_{safe_customer}_{datetime.now().strftime('%Y%m%d')}.pdf"

    results = []
    sent_channels = []

    # ----- EMAIL -----
    if channel in ("email", "both") and is_email_configured():
        if email:
            subject = f"Quotation from Vijaylaxmi Trading Company — {product_name}"
            body = build_quotation_email_body(customer, product_name, quantity, total)
            result = send_email(email, subject, body, pdf_bytes, filename)
            results.append(("email", result))
            if result.get("success"):
                sent_channels.append("email")
        else:
            results.append(("email", {"success": False, "error": "No email address"}))
    elif channel in ("email", "both"):
        results.append(("email", {"success": False, "error": "Email not configured"}))

    # ----- WHATSAPP -----
    if channel in ("whatsapp", "both") and is_whatsapp_configured():
        if phone:
            result = send_quotation_whatsapp(
                phone, customer, product_name, quantity, total, pdf_bytes, filename
            )
            results.append(("whatsapp", result))
            if result.get("success"):
                sent_channels.append("whatsapp")
        else:
            results.append(("whatsapp", {"success": False, "error": "No phone number"}))
    elif channel in ("whatsapp", "both"):
        results.append(("whatsapp", {"success": False, "error": "WhatsApp not configured"}))

    # Log to DB
    if sent_channels:
        for ch in sent_channels:
            save_quotation({
                "lead_id": lead.get("id"),
                "quotation_no": quotation_no,
                "customer": customer,
                "product_id": lead.get("product_id"),
                "quantity_kg": quantity,
                "rate_per_kg": rate_per_kg,
                "total_value": total,
                "channel": ch,
                "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "sent",
            })

    # Return combined result
    all_success = all(r.get("success") for _, r in results)
    any_success = any(r.get("success") for _, r in results)

    if all_success:
        return {"success": True, "channel": "/".join(sent_channels), "error": None}
    elif any_success:
        failed = [(ch, r.get("error")) for ch, r in results if not r.get("success")]
        return {"success": True, "channel": "/".join(sent_channels), "error": f"Partial: {failed}"}
    else:
        errors = [r.get("error", "Unknown error") for _, r in results]
        return {"success": False, "channel": "", "error": " | ".join(errors)}
