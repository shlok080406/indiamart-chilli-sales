"""
Tests for lead/enquiry database operations.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import os

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_insert_lead_returns_id():
    """Inserting a lead returns the new lead id."""
    from database.pricing_db import insert_lead, get_connection

    lead_data = {
        "customer": "Test Customer",
        "phone": "9876543210",
        "location": "Mumbai",
        "status": "New",
        "quantity_kg": 500.0,
        "parsed_variety": "Teja / Guntur",
        "is_parsed": 1,
    }

    lead_id = insert_lead(lead_data)
    assert isinstance(lead_id, int)
    assert lead_id > 0

    # Verify it was inserted
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT customer FROM leads WHERE id = ?", (lead_id,))
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row["customer"] == "Test Customer"


def test_get_all_leads_returns_list():
    """get_all_leads returns a list of dicts."""
    from database.pricing_db import get_all_leads

    leads = get_all_leads()
    assert isinstance(leads, list)


def test_update_lead_status():
    """Updating a lead's status persists to the database."""
    from database.pricing_db import insert_lead, update_lead_status, get_connection

    lead_id = insert_lead({"customer": "Status Test", "status": "New"})

    update_lead_status(lead_id, "Follow-up", "2026-09-15")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status, next_follow_up FROM leads WHERE id = ?", (lead_id,))
    row = cur.fetchone()
    conn.close()

    assert row["status"] == "Follow-up"
    assert row["next_follow_up"] == "2026-09-15"


def test_pricing_tiers_crud():
    """Saving and retrieving pricing tiers works correctly."""
    from database.pricing_db import save_tiers, get_tiers_for_product

    tiers = [
        {"min_qty": 1, "max_qty": 100, "rate_per_kg": 150.0},
        {"min_qty": 100, "max_qty": None, "rate_per_kg": 130.0},
    ]

    save_tiers("test_tier_product", tiers)
    retrieved = get_tiers_for_product("test_tier_product")

    assert len(retrieved) == 2
    assert retrieved[0]["rate_per_kg"] == 150.0
    assert retrieved[1]["max_qty"] is None


def test_get_tier_for_quantity():
    """Tier lookup returns the correct tier for a given quantity."""
    from database.pricing_db import save_tiers, get_tier_for_quantity

    tiers = [
        {"min_qty": 1, "max_qty": 50, "rate_per_kg": 200.0},
        {"min_qty": 50, "max_qty": 500, "rate_per_kg": 180.0},
        {"min_qty": 500, "max_qty": None, "rate_per_kg": 160.0},
    ]

    save_tiers("tier_lookup_product", tiers)

    assert get_tier_for_quantity("tier_lookup_product", 25)["rate_per_kg"] == 200.0
    assert get_tier_for_quantity("tier_lookup_product", 100)["rate_per_kg"] == 180.0
    assert get_tier_for_quantity("tier_lookup_product", 1000)["rate_per_kg"] == 160.0
    assert get_tier_for_quantity("nonexistent", 50) is None


def test_quotation_history():
    """Saving and retrieving quotation history works."""
    from database.pricing_db import save_quotation, get_quotation_history

    quotation = {
        "lead_id": 1,
        "quotation_no": "QTN-TEST-001",
        "customer": "Test Customer",
        "product_id": "teja_guntur",
        "quantity_kg": 500,
        "rate_per_kg": 150.0,
        "total_value": 75000.0,
        "channel": "email",
        "status": "sent",
    }

    qid = save_quotation(quotation)
    assert isinstance(qid, int)

    history = get_quotation_history()
    assert len(history) >= 1
