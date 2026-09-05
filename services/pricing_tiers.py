"""
Quantity-based tiered pricing service.

Each product can have multiple price tiers:
- 1-50 kg  -> rate_per_kg
- 50-500 kg -> rate_per_kg
- 500+ kg   -> rate_per_kg

The quoting page uses the tier that matches the entered quantity.
"""

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
TIERS_FILE = ROOT / "data" / "pricing_tiers.json"


def load_tiers():
    """Load pricing tiers from JSON file."""
    try:
        with open(TIERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_tiers_to_file(tiers_data: dict):
    """Save pricing tiers to JSON file."""
    with open(TIERS_FILE, "w", encoding="utf-8") as f:
        json.dump(tiers_data, f, indent=4, ensure_ascii=False)


def get_tiers_for_product(product_id: str):
    """Return tier list for a product from the JSON file."""
    all_tiers = load_tiers()
    return all_tiers.get(product_id, [])


def get_rate_for_quantity(product_id: str, quantity: float):
    """Return the applicable rate per kg for a given quantity.

    Falls back to the first tier if none match, or returns None if no tiers defined.
    """
    tiers = get_tiers_for_product(product_id)
    if not tiers:
        return None

    for tier in tiers:
        min_qty = tier.get("min_qty", 0)
        max_qty = tier.get("max_qty")

        if max_qty is None or quantity <= max_qty:
            return tier["rate_per_kg"]

    # Quantity exceeds all defined tiers — use last tier
    if tiers:
        return tiers[-1]["rate_per_kg"]

    return None


def add_tier(product_id: str, min_qty: float, max_qty: float, rate_per_kg: float):
    """Add a tier to a product and persist."""
    all_tiers = load_tiers()

    if product_id not in all_tiers:
        all_tiers[product_id] = []

    # Remove any existing tier with the same min_qty
    all_tiers[product_id] = [
        t for t in all_tiers[product_id] if t.get("min_qty") != min_qty
    ]

    all_tiers[product_id].append({
        "min_qty": min_qty,
        "max_qty": max_qty,
        "rate_per_kg": rate_per_kg,
    })

    # Sort by min_qty
    all_tiers[product_id].sort(key=lambda t: t["min_qty"])

    save_tiers_to_file(all_tiers)


def remove_tier(product_id: str, min_qty: float):
    """Remove a tier by min_qty."""
    all_tiers = load_tiers()

    if product_id in all_tiers:
        all_tiers[product_id] = [
            t for t in all_tiers[product_id] if t.get("min_qty") != min_qty
        ]
        save_tiers_to_file(all_tiers)
