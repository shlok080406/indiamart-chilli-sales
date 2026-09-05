"""
Tests for the quantity-based tiered pricing service.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, mock_open

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.pricing_tiers import (
    get_tiers_for_product,
    get_rate_for_quantity,
    add_tier,
    remove_tier,
)


MOCK_TIERS = {
    "test_product": [
        {"min_qty": 1, "max_qty": 50, "rate_per_kg": 200.0},
        {"min_qty": 50, "max_qty": 500, "rate_per_kg": 180.0},
        {"min_qty": 500, "max_qty": None, "rate_per_kg": 150.0},
    ]
}


def test_get_tiers_for_product():
    """Test that tiers are returned for a valid product id."""
    with patch("services.pricing_tiers.load_tiers", return_value=MOCK_TIERS):
        tiers = get_tiers_for_product("test_product")
        assert len(tiers) == 3
        assert tiers[0]["min_qty"] == 1
        assert tiers[0]["rate_per_kg"] == 200.0


def test_get_tiers_unknown_product():
    """Unknown product id returns empty list."""
    with patch("services.pricing_tiers.load_tiers", return_value=MOCK_TIERS):
        tiers = get_tiers_for_product("nonexistent")
        assert tiers == []


def test_get_rate_small_quantity():
    """Small quantity uses first tier."""
    with patch("services.pricing_tiers.load_tiers", return_value=MOCK_TIERS):
        rate = get_rate_for_quantity("test_product", 10)
        assert rate == 200.0


def test_get_rate_medium_quantity():
    """Medium quantity uses middle tier."""
    with patch("services.pricing_tiers.load_tiers", return_value=MOCK_TIERS):
        rate = get_rate_for_quantity("test_product", 100)
        assert rate == 180.0


def test_get_rate_large_quantity():
    """Large quantity uses highest tier."""
    with patch("services.pricing_tiers.load_tiers", return_value=MOCK_TIERS):
        rate = get_rate_for_quantity("test_product", 1000)
        assert rate == 150.0


def test_get_rate_no_tiers():
    """No tiers defined returns None."""
    with patch("services.pricing_tiers.load_tiers", return_value={}):
        rate = get_rate_for_quantity("test_product", 50)
        assert rate is None


def test_add_tier_appends():
    """Adding a tier appends to the existing list."""
    initial = {"test_product": [{"min_qty": 1, "max_qty": 50, "rate_per_kg": 200.0}]}
    with patch("services.pricing_tiers.load_tiers", return_value=initial), \
         patch("services.pricing_tiers.save_tiers_to_file") as save_mock:
        add_tier("test_product", 50, 500, 180.0)
        saved = save_mock.call_args[0][0]
        assert len(saved["test_product"]) == 2


def test_add_tier_replaces_existing():
    """Adding a tier with the same min_qty replaces the existing one."""
    initial = {"test_product": [{"min_qty": 1, "max_qty": 50, "rate_per_kg": 200.0}]}
    with patch("services.pricing_tiers.load_tiers", return_value=initial), \
         patch("services.pricing_tiers.save_tiers_to_file") as save_mock:
        add_tier("test_product", 1, 100, 250.0)
        saved = save_mock.call_args[0][0]
        assert len(saved["test_product"]) == 1
        assert saved["test_product"][0]["rate_per_kg"] == 250.0


def test_remove_tier():
    """Removing a tier removes it from the list."""
    initial = {
        "test_product": [
            {"min_qty": 1, "max_qty": 50, "rate_per_kg": 200.0},
            {"min_qty": 50, "max_qty": 500, "rate_per_kg": 180.0},
        ]
    }
    with patch("services.pricing_tiers.load_tiers", return_value=initial), \
         patch("services.pricing_tiers.save_tiers_to_file") as save_mock:
        remove_tier("test_product", 1)
        saved = save_mock.call_args[0][0]
        assert len(saved["test_product"]) == 1
        assert saved["test_product"][0]["min_qty"] == 50
