"""
AI-powered enquiry parser.

Uses Anthropic's Claude to parse raw IndiaMART enquiry text into a structured
lead dict: customer, quantity (kg), variety, location, requirement.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# Allow imports from sibling modules
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_products() -> list:
    """Load product catalogue for variety matching."""
    products_file = ROOT / "data" / "products.json"
    try:
        with open(products_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _get_claude_client():
    """Return an Anthropic client using env var or secrets.json."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        secrets_file = ROOT / "data" / "secrets.json"
        try:
            with open(secrets_file, "r", encoding="utf-8") as f:
                secrets = json.load(f)
                api_key = secrets.get("anthropic_api_key") or secrets.get("openrouter_api_key")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    if not api_key:
        return None

    # Try Anthropic SDK first
    try:
        import anthropic
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        pass

    # Fall back to OpenRouter-compatible client via requests
    return None


PRODUCT_NAMES = [p["name"].lower() for p in _load_products()]
PRODUCT_IDS = {p["name"].lower(): p["id"] for p in _load_products()}


SYSTEM_PROMPT = f"""You are a sales assistant parsing IndiaMART chilli powder enquiries.

Given a raw enquiry text, extract and return a JSON object with these exact keys:
- customer (string): the sender's name or company
- phone (string): phone number if visible
- location (string): city or region
- requirement (string): what the customer wants, as written
- parsed_quantity (number): quantity in kg as a plain number (e.g. 500 for "500 kg" or "5 quintal"). Use null if not stated.
- parsed_variety (string): the chilli variety matched from this list: {json.dumps(PRODUCT_NAMES)}. Return null if not clear.

Rules:
- If quantity is in quintals, convert: 1 quintal = 100 kg.
- If quantity is in bags or packets, estimate 25 kg per unit unless otherwise stated.
- Match variety loosely: "Teja", "gunter", "guntru" → "Teja / Guntur". "Byadgi", "byadagi" → "Pure Byadgi".
- Return ONLY the JSON object, no extra text.
- If nothing useful can be extracted, return {{}}."""


def parse_enquiry(raw_text: str) -> Dict:
    """
    Parse a raw enquiry text using Claude AI.

    Returns a dict with keys: customer, phone, location, requirement,
    parsed_quantity (float or None), parsed_variety (string or None).
    Falls back to rule-based extraction if the AI call fails.
    """
    if not raw_text or not raw_text.strip():
        return {}

    client = _get_claude_client()

    if client:
        try:
            # Use Anthropic Messages API
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": raw_text}],
            )
            parsed = json.loads(response.content[0].text)
            return _enrich_parsed(parsed)
        except Exception:
            pass

    # Fall back to rule-based extraction
    return _rule_based_parse(raw_text)


def _enrich_parsed(parsed: Dict) -> Dict:
    """Map parsed variety name to product id and clean up."""
    variety = parsed.get("parsed_variety")
    if variety:
        variety_lower = variety.lower()
        product_id = PRODUCT_IDS.get(variety_lower)
        if product_id:
            parsed["product_id"] = product_id
        else:
            # Try fuzzy match
            for name, pid in PRODUCT_IDS.items():
                if any(word in variety_lower for word in name.split()):
                    parsed["product_id"] = pid
                    parsed["parsed_variety"] = name.title()
                    break

    return parsed


def _rule_based_parse(text: str) -> Dict:
    """Fallback rule-based parser when AI is unavailable."""
    import re

    result = {}

    # Quantity extraction
    quantity_patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)",
        r"(\d+(?:\.\d+)?)\s*(?:quintal|qtl|q)",
        r"(\d+(?:\.\d+)?)\s*(?:bags?|packets?)",
        r"need[s]?\s+(\d+(?:\.\d+)?)\s*kg",
        r"requirement\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*kg",
        r"looking\s+for\s+(\d+(?:\.\d+)?)\s*kg",
        r"(\d+(?:\.\d+)?)\s*kg",
    ]

    quantity = None
    for pattern in quantity_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            quantity = float(match.group(1))
            # Convert quintals to kg
            if "quintal" in pattern.lower():
                quantity *= 100
            # Convert bags to kg (assume 25 kg per bag)
            if "bag" in pattern.lower() or "packet" in pattern.lower():
                quantity *= 25
            result["parsed_quantity"] = quantity
            break

    # Variety detection
    variety_keywords = {
        "teja": "Teja / Guntur",
        "guntru": "Teja / Guntur",
        "gunter": "Teja / Guntur",
        "premium teja": "Teja premium / Guntur",
        "resham": "Resham patti / Byadgi blend",
        "byadgi": "Pure Byadgi",
        "byadagi": "Pure Byadgi",
        "kashmiri": "Kashmiri byadgi / Kashmiri",
    }

    text_lower = text.lower()
    for keyword, variety in variety_keywords.items():
        if keyword in text_lower:
            result["parsed_variety"] = variety
            result["product_id"] = PRODUCT_IDS.get(variety.lower())
            break

    # Phone extraction
    phone_match = re.search(r"[\+]?[\d\s\-]{10,15}", text)
    if phone_match:
        result["phone"] = phone_match.group().strip()

    # Customer / company name (rough heuristic: first word or capitalized phrase)
    name_match = re.search(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    if name_match:
        result["customer"] = name_match.group(1)

    # Location
    city_match = re.search(
        r"(?:from|in|located|living|city)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        text,
    )
    if city_match:
        result["location"] = city_match.group(1)

    result["requirement"] = text[:200]

    return result
