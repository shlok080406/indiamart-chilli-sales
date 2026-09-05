"""Test that dashboard.py parses and imports without errors."""
import sys
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "app" / "dashboard.py"


def test_dashboard_parses():
    """Check that dashboard.py is valid Python."""
    source = DASHBOARD.read_text(encoding="utf-8")
    tree = ast.parse(source)
    print(f"dashboard.py parsed OK ({len(tree.body)} top-level nodes)")
    return True


def test_dashboard_imports():
    """Check that all non-streamlit imports work."""
    # We can't import streamlit without a tty, so we check the imports separately
    sys.path.insert(0, str(ROOT))

    from database.pricing_db import initialize_database
    from services.pricing_tiers import get_tiers_for_product
    from services.followup_scheduler import calculate_next_follow_up
    from services.enquiry_parser import _rule_based_parse

    print("All service imports OK")
    return True


if __name__ == "__main__":
    ok = test_dashboard_parses() and test_dashboard_imports()
    sys.exit(0 if ok else 1)
