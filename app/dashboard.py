import json
import sys
from pathlib import Path
from datetime import date, datetime

import streamlit as st
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# =========================================================
# PROJECT SETUP
# =========================================================

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ASSETS_DIR = ROOT / "assets"
LOGO_SVG = ASSETS_DIR / "logo.svg"
FAVICON_PNG = ASSETS_DIR / "favicon-32.png"

from database.pricing_db import (
    initialize_database,
    save_price,
    get_current_price,
    get_all_leads,
    update_lead_status,
    get_quotation_history,
)
from services.pricing_tiers import get_tiers_for_product, add_tier, remove_tier
from services.followup_scheduler import (
    calculate_next_follow_up,
    get_overdue_leads,
    get_due_today_leads,
    get_upcoming_leads,
)

# Import the enquiry ingest page module
try:
    from app.enquiry_ingest import render_enquiries_page
    HAS_ENQUIRY_INGEST = True
except Exception:
    HAS_ENQUIRY_INGEST = False

# =========================================================
# FILES
# =========================================================

PRODUCTS_FILE = ROOT / "data" / "products.json"
LEADS_FILE = ROOT / "data" / "leads.json"
RULES_FILE = ROOT / "data" / "business_rules.json"
CUSTOMERS_FILE = ROOT / "data" / "customers.json"
USERS_FILE = ROOT / "data" / "users.json"


def load_json(file_path, default):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def parse_quantity(value, default=None):
    """Safely extract a float from a quantity field that may contain units like 'kg'."""
    if not value:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        import re
        match = re.search(r"[\d,]+(?:\.\d+)?", str(value))
        if match:
            return float(match.group(0).replace(",", ""))
        return default


products = load_json(PRODUCTS_FILE, [])
leads = load_json(LEADS_FILE, [])
rules = load_json(RULES_FILE, {})
customers = load_json(CUSTOMERS_FILE, [])
users_data = load_json(USERS_FILE, {"users": []})

initialize_database()

# =========================================================
# PAGE CONFIG — must be the first Streamlit command
# =========================================================

def _logo_data_uri() -> str:
    """Return a base64 data URI for the logo SVG, or empty string if missing."""
    import base64
    if LOGO_SVG.exists():
        try:
            svg = LOGO_SVG.read_text(encoding="utf-8")
            b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
            return f"data:image/svg+xml;base64,{b64}"
        except Exception:
            return ""
    return ""


# Prefer the SVG logo as the favicon. Fall back to PNG, then the chili emoji.
if LOGO_SVG.exists():
    _page_icon = _logo_data_uri()
elif FAVICON_PNG.exists():
    _page_icon = str(FAVICON_PNG)
else:
    _page_icon = ""

st.set_page_config(
    page_title="LEHAR — Sales Automation",
    page_icon=_page_icon or "chili",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================
# AUTHENTICATION
# =========================================================

USERS = {u["username"]: u for u in users_data.get("users", [])}


def login_user(username: str, password: str):
    """Authenticate a user. Returns the user dict or None."""
    user = USERS.get(username)
    if user and user["password"] == password:
        return user
    return None


def logout_user():
    """Clear the logged-in user from session state."""
    st.session_state["logged_in"] = False
    st.session_state["user"] = None
    st.rerun()


def add_user(username: str, password: str, role: str = "user", full_name: str = ""):
    """Add a new user. Returns True if successful, False if username exists."""
    if username in USERS:
        return False
    new_user = {
        "username": username,
        "password": password,
        "role": role,
        "full_name": full_name or username,
        "created_at": datetime.now().strftime("%Y-%m-%d"),
    }
    USERS[username] = new_user
    users_data["users"].append(new_user)
    save_json(USERS_FILE, users_data)
    return True


def render_login_screen():
    """Render the login page."""
    # Center the login form
    spacer_l, center_col, spacer_r = st.columns([1, 2, 1])

    with center_col:
        st.markdown("")
        _logo_uri = _logo_data_uri()
        if _logo_uri:
            st.markdown(
                f"<div style='text-align:center; margin-bottom:12px;'>"
                f"<img src='{_logo_uri}' width='56' height='56' "
                f"style='filter:drop-shadow(0 4px 10px rgba(0,0,0,0.45));'>"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.markdown("### LEHAR")
        st.markdown(
            "<p style='color: var(--text-muted); font-size: 13px; "
            "letter-spacing: 0.08em; text-transform: uppercase; "
            "margin: 4px 0 0;'>Every enquiry, answered. Every lead, closed.</p>",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown("Sign in to your account")

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

            if submitted:
                user = login_user(username, password)
                if user:
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = user
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

        st.markdown("---")
        st.caption("Contact the administrator for login credentials.")


# =========================================================
# INIT SESSION STATE
# =========================================================

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user" not in st.session_state:
    st.session_state["user"] = None

# Show login screen if not logged in
if not st.session_state["logged_in"]:
    render_login_screen()
    st.stop()


# =========================================================
# CSS — Spotify-inspired dark theme with chilli red accent
# Font: Manrope (geometric sans-serif, similar to Circular)
# =========================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800;900&display=swap');

    :root {
        --bg-base:      #121212;
        --bg-card:      #181818;
        --bg-hover:     #282828;
        --bg-overlay:   rgba(255, 255, 255, 0.07);
        --accent:       #E11D48;
        --accent-hover: #F43F5E;
        --accent-glow:  rgba(225, 29, 72, 0.25);
        --text:         #FFFFFF;
        --text-muted:   #B3B3B3;
        --border:       rgba(255, 255, 255, 0.08);
    }

    /* ── Global reset ── */
    html, body, [class*="css"], .stApp {
        font-family: 'Manrope', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    .stApp {
        background: var(--bg-base);
        color: var(--text);
    }

    /* ── Layout ── */
    .block-container {
        max-width: 1500px;
        padding: 2rem 2.5rem 6rem;
    }

    /* ── Typography ── */
    h1, h2, h3, h4 {
        font-family: 'Manrope', sans-serif !important;
        letter-spacing: -0.04em;
        color: var(--text) !important;
        font-weight: 800 !important;
    }

    /* ── Hero banner ── */
    .hero {
        background: linear-gradient(135deg, #7C1D3D 0%, var(--accent) 100%);
        border-radius: 16px;
        padding: 44px 40px 40px;
        margin-bottom: 32px;
        position: relative;
        overflow: hidden;
    }

    .hero::before {
        content: '';
        position: absolute;
        inset: 0;
        background: radial-gradient(ellipse at 80% 50%, rgba(225,29,72,0.35) 0%, transparent 70%);
        pointer-events: none;
    }

    .hero h1 {
        font-size: 48px;
        font-weight: 900;
        margin: 0;
        color: #FFFFFF !important;
        letter-spacing: -0.05em;
        position: relative;
    }

    .hero p {
        color: rgba(255, 255, 255, 0.82);
        margin: 10px 0 0;
        font-size: 15px;
        font-weight: 500;
        letter-spacing: 0.01em;
        position: relative;
    }

    .hero .hero-date {
        margin-top: 18px;
        font-size: 12px;
        font-weight: 700;
        color: rgba(255,255,255,0.55);
        text-transform: uppercase;
        letter-spacing: 0.1em;
        position: relative;
    }

    /* ── Metric tiles ── */
    [data-testid="stMetric"] {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 22px 24px 20px;
        min-height: 120px;
        transition: background 0.2s ease, transform 0.15s ease;
    }

    [data-testid="stMetric"]:hover {
        background: var(--bg-hover);
        transform: translateY(-2px);
    }

    [data-testid="stMetricLabel"] {
        color: var(--text-muted) !important;
        font-size: 10.5px !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.09em;
    }

    [data-testid="stMetricValue"] {
        color: var(--text) !important;
        font-size: 34px !important;
        font-weight: 900 !important;
        letter-spacing: -0.04em;
        margin-top: 8px;
    }

    /* ── Section headers ── */
    .section-head {
        font-size: 20px;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin-bottom: 16px;
        color: var(--text) !important;
    }

    /* ── Cards / containers ── */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 14px !important;
        padding: 20px !important;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: #000000;
        border-right: 1px solid var(--border);
    }

    section[data-testid="stSidebar"] .block-container {
        padding: 1.8rem 0.8rem;
    }

    section[data-testid="stSidebar"] h1 {
        font-size: 22px !important;
        font-weight: 900 !important;
        letter-spacing: -0.04em;
    }

    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: var(--text-muted);
        font-size: 12px;
    }

    /* ── Radio nav — pill-style items ── */
    section[data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 6px;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] > label {
        border-radius: 10px;
        padding: 12px 16px;
        transition: background 0.15s ease;
        font-size: 14px;
        font-weight: 600;
        color: var(--text-muted);
        background: transparent;
        border: none;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
        background: var(--bg-overlay);
        color: var(--text);
    }

    /* Active item — subtle left accent bar */
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
        background: rgba(225, 29, 72, 0.15);
        color: var(--text);
        position: relative;
    }

    /* ── Buttons — pill shape ── */
    .stButton > button {
        border-radius: 999px !important;
        min-height: 44px;
        font-family: 'Manrope', sans-serif !important;
        font-size: 13.5px;
        font-weight: 700;
        border: none;
        transition: all 0.18s ease;
        padding: 0 28px !important;
        letter-spacing: 0.01em;
    }

    .stButton > button:hover {
        transform: scale(1.025);
    }

    .stButton > button:active {
        transform: scale(0.98);
    }

    /* Primary accent button */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button {
        background: var(--accent) !important;
        color: #FFFFFF !important;
    }

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover {
        background: var(--accent-hover) !important;
        box-shadow: 0 4px 20px var(--accent-glow);
    }

    /* Secondary / ghost button */
    .stButton > button:not([kind="primary"]) {
        background: var(--bg-hover) !important;
        color: var(--text) !important;
        border: 1px solid var(--border) !important;
    }

    .stButton > button:not([kind="primary"]):hover {
        background: #333333 !important;
        border-color: rgba(255,255,255,0.15) !important;
    }

    /* ── Inputs ── */
    .stTextInput input,
    .stNumberInput input,
    .stTextArea textarea {
        border-radius: 10px !important;
        background: var(--bg-hover) !important;
        border: 1px solid var(--border) !important;
        color: var(--text) !important;
        font-family: 'Manrope', sans-serif !important;
        font-size: 14px !important;
    }

    .stTextInput input:focus,
    .stNumberInput input:focus,
    .stTextArea textarea:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 2px var(--accent-glow) !important;
    }

    .stSelectbox div[data-baseweb="select"] {
        border-radius: 10px !important;
        background: var(--bg-hover) !important;
        border: 1px solid var(--border) !important;
    }

    .stSelectbox input {
        color: var(--text) !important;
        font-family: 'Manrope', sans-serif !important;
    }

    /* ── Expanders / accordions ── */
    [data-testid="stExpander"] {
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
        background: var(--bg-card) !important;
        overflow: hidden;
    }

    [data-testid="stExpander"] summary {
        font-weight: 600;
        font-size: 15px;
    }

    /* ── Dividers ── */
    hr {
        border-color: var(--border) !important;
        margin: 1.5rem 0 !important;
    }

    /* ── Alerts ── */
    .stAlert {
        border-radius: 12px !important;
        border: none !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 1px solid var(--border);
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        font-weight: 600;
        font-size: 14px;
        color: var(--text-muted);
        padding: 8px 16px;
    }

    .stTabs [data-baseweb="tab"]:hover {
        color: var(--text);
        background: var(--bg-overlay);
    }

    .stTabs [aria-selected="true"] {
        color: var(--text) !important;
        border-bottom: 2px solid var(--accent) !important;
    }

    /* ── Download button ── */
    .stDownloadButton > button {
        background: var(--accent) !important;
        color: white !important;
        border-radius: 999px !important;
        min-height: 44px;
        font-weight: 700;
        font-family: 'Manrope', sans-serif !important;
    }

    .stDownloadButton > button:hover {
        background: var(--accent-hover) !important;
        box-shadow: 0 4px 20px var(--accent-glow);
        transform: scale(1.025);
    }

    /* ── Progress bar / spinner ── */
    .stSpinner > div {
        border-color: var(--accent) !important;
    }

    /* ── Tooltips ── */
    [data-testid="stTooltipIcon"] {
        color: var(--text-muted);
    }

    /* ── Inline spinner (during fetch) ── */
    [data-testid="stStatusWidget"] {
        color: var(--text-muted);
    }
    </style>
    """,
    unsafe_allow_html=True,
)
# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    # User info
    current_user = st.session_state.get("user", {})
    user_name = current_user.get("full_name", current_user.get("username", "User"))
    user_role = current_user.get("role", "user")
    st.markdown(f"**{user_name}**")
    st.caption(f"Role: {user_role.title()}")
    st.divider()

    if st.button("Logout", use_container_width=True):
        logout_user()

    st.divider()
    # Brand block: logo + name + tagline
    _logo_uri = _logo_data_uri()
    if _logo_uri:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<img src="{_logo_uri}" width="42" height="42" '
            f'style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.4));">'
            f'<div>'
            f'<div style="font-size:1.4rem;font-weight:700;'
            f'letter-spacing:0.12em;line-height:1;">LEHAR</div>'
            f'<div style="font-size:0.7rem;color:#9aa3ad;'
            f'letter-spacing:0.08em;margin-top:4px;">SALES AUTOMATION</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown("# LEHAR")
    st.caption("Every enquiry, answered. Every lead, closed.")
    st.caption("IndiaMART sales automation")

    st.divider()

    st.markdown("### Navigation")

    page = st.radio(
        "Navigation",
        [
            "Dashboard",
            "Enquiries",
            "Products",
            "Pricing Tiers",
            "Update Prices",
            "Leads",
            "Follow-ups",
            "Quotation",
            "Customers",
        ] + (["User Management"] if current_user.get("role") == "admin" else []),
        label_visibility="collapsed",
    )

    st.divider()

    st.markdown("### Business")

    st.write(f"**{len(products)}** products")
    st.write(f"**{len(leads)}** active leads")

    st.write(
        f"Price review: "
        f"**{rules.get('price_review_days', 15)} days**"
    )

    st.divider()

    st.caption(
        "Prices should be manually verified before sending quotations."
    )
# =========================================================
# PDF QUOTATION HELPER
# =========================================================

def build_quotation_pdf(
    customer,
    location,
    product,
    quantity,
    price,
    packaging,
    quotation_date,
):
    buffer = BytesIO()

    quotation_no = (
        f"QTN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )

    validity_days = 7

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
        title="LEHAR Quotation",
        author="LEHAR Sales Automation",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "QuoteTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "QuoteSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#666666"),
        spaceAfter=6,
    )

    contact_style = ParagraphStyle(
        "Contact",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#555555"),
        spaceAfter=18,
    )

    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.HexColor("#555555"),
    )

    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
    )

    total_style = ParagraphStyle(
        "Total",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        alignment=TA_LEFT,
    )

    note_style = ParagraphStyle(
        "Note",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#555555"),
    )

    story = []

    # =====================================================
    # COMPANY HEADER
    # =====================================================

    story.append(
        Paragraph(
            "LEHAR",
            title_style,
        )
    )

    story.append(
        Paragraph(
            "Red Chilli Powder & Spices",
            subtitle_style,
        )
    )

    story.append(
        Paragraph(
            "<b>Phone:</b> 9740218812",
            contact_style,
        )
    )

    # =====================================================
    # CUSTOMER DETAILS
    # =====================================================

    customer_table = Table(
        [
            [
                Paragraph(
                    "<b>Customer / Company</b>",
                    label_style,
                ),
                Paragraph(
                    str(customer),
                    value_style,
                ),
            ],
            [
                Paragraph(
                    "<b>Location</b>",
                    label_style,
                ),
                Paragraph(
                    str(location or "Not provided"),
                    value_style,
                ),
            ],
            [
                Paragraph(
                    "<b>Date</b>",
                    label_style,
                ),
                Paragraph(
                    str(quotation_date),
                    value_style,
                ),
            ],
            [
                Paragraph(
                    "<b>Quotation No.</b>",
                    label_style,
                ),
                Paragraph(
                    str(quotation_no),
                    value_style,
                ),
            ],
            [
                Paragraph(
                    "<b>Quotation Validity</b>",
                    label_style,
                ),
                Paragraph(
                    f"{validity_days} Days",
                    value_style,
                ),
            ],
        ],
        colWidths=[145, 365],
        hAlign="LEFT",
    )

    customer_table.setStyle(
        TableStyle(
            [
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#DDDDDD"),
                ),
            ]
        )
    )

    story += [
        customer_table,
        Spacer(1, 22),
    ]

    # =====================================================
    # QUOTATION
    # =====================================================

    story.append(
        Paragraph(
            "QUOTATION",
            styles["Heading2"],
        )
    )

    line_total = quantity * price

    item_table = Table(
        [
            [
                Paragraph(
                    "<b>Product</b>",
                    label_style,
                ),
                Paragraph(
                    "<b>Quantity</b>",
                    label_style,
                ),
                Paragraph(
                    "<b>Rate</b>",
                    label_style,
                ),
                Paragraph(
                    "<b>Total</b>",
                    label_style,
                ),
            ],
            [
                Paragraph(
                    str(product),
                    value_style,
                ),
                Paragraph(
                    f"{quantity:,.0f} kg",
                    value_style,
                ),
                Paragraph(
                    f"Rs. {price:,.2f}/kg",
                    value_style,
                ),
                Paragraph(
                    f"Rs. {line_total:,.2f}",
                    value_style,
                ),
            ],
        ],
        colWidths=[245, 85, 85, 95],
        hAlign="LEFT",
    )

    item_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#F1F2F4"),
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#D5D7DB"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
            ]
        )
    )

    story += [
        item_table,
        Spacer(1, 16),
    ]

    # =====================================================
    # TERMS
    # =====================================================

    terms_table = Table(
        [
            [
                Paragraph(
                    "<b>Packaging</b>",
                    label_style,
                ),
                Paragraph(
                    str(
                        packaging
                        or "To be confirmed"
                    ),
                    value_style,
                ),
            ],
            [
                Paragraph(
                    "<b>Payment / Delivery</b>",
                    label_style,
                ),
                Paragraph(
                    "To be confirmed with customer",
                    value_style,
                ),
            ],
                   [
            Paragraph(
                "<b>Quotation Validity</b>",
                label_style,
            ),
            Paragraph(
                f"{validity_days} Days",
                value_style,
            ),
        ],
        ],
        colWidths=[145, 365],
        hAlign="LEFT",
    )

    terms_table.setStyle(
        TableStyle(
            [
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
            ]
        )
    )

    story += [
        terms_table,
        Spacer(1, 20),
    ]

    # =====================================================
    # TOTAL
    # =====================================================

    total_table = Table(
        [
            [
                Paragraph(
                    f"<b>Total Quotation Value: "
                    f"Rs. {line_total:,.2f}</b>",
                    total_style,
                )
            ]
        ],
        colWidths=[510],
    )

    total_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#F1F2F4"),
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.6,
                    colors.HexColor("#D5D7DB"),
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    12,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    12,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    12,
                ),
            ]
        )
    )

    story += [
        total_table,
        Spacer(1, 20),
    ]

    # =====================================================
    # NOTES
    # =====================================================

    story.append(
        Paragraph(
            "<b>Important:</b> "
            "Verify price, availability and delivery "
            "terms before sending this quotation.",
            note_style,
        )
    )

    story += [
        Spacer(1, 18),
        Paragraph(
            "This quotation is subject to final confirmation.",
            note_style,
        ),
    ]

    doc.build(story)

    buffer.seek(0)

    return buffer.getvalue()

# =========================================================
# DASHBOARD
# =========================================================

if page == "Dashboard":

    st.markdown(
        """
        <div class="hero">
            <h1>Sales Command Centre</h1>
            <p>Every enquiry, answered. Every lead, closed.</p>
            <div class="hero-date">LEHAR · {today}</div>
        </div>
        """.format(today=date.today().strftime("%A, %d %B %Y")),
        unsafe_allow_html=True,
    )

    # Load leads from DB
    all_db_leads = get_all_leads()

    # -----------------------------------------------------
    # PIPELINE FUNNEL
    # -----------------------------------------------------

    new_count = sum(1 for l in all_db_leads if str(l.get("status", "New")).lower() == "new")
    followup_count = sum(1 for l in all_db_leads if str(l.get("status", "")).lower() == "follow-up")
    quoted_count = sum(1 for l in all_db_leads if str(l.get("status", "")).lower() == "quoted")
    converted_count = sum(1 for l in all_db_leads if str(l.get("status", "")).lower() == "converted")
    lost_count = sum(1 for l in all_db_leads if str(l.get("status", "")).lower() == "lost")

    overdue_followups = len(get_overdue_leads(all_db_leads))
    due_today_followups = len(get_due_today_leads(all_db_leads))

    st.markdown('<p class="section-head">Pipeline</p>', unsafe_allow_html=True)

    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("New", new_count)
    p2.metric("Follow-up", followup_count)
    p3.metric("Quoted", quoted_count)
    p4.metric("Converted", converted_count)
    p5.metric("Lost", lost_count)

    # Conversion rate
    total_leads = len(all_db_leads)
    if total_leads > 0:
        conversion_pct = (converted_count / total_leads) * 100
    else:
        conversion_pct = 0
    st.caption(f"Overall conversion rate: **{conversion_pct:.1f}%** ({converted_count} of {total_leads})")

    st.markdown("<hr>", unsafe_allow_html=True)

    # -----------------------------------------------------
    # FOLLOW-UP ALERTS
    # -----------------------------------------------------

    if overdue_followups > 0 or due_today_followups > 0:
        st.markdown('<p class="section-head">Follow-up Alerts</p>', unsafe_allow_html=True)
        col_a1, col_a2 = st.columns(2)
        col_a1.warning(f"[!] {overdue_followups} overdue follow-up(s)")
        col_a2.info(f"[i] {due_today_followups} due today")
        st.markdown("<hr>", unsafe_allow_html=True)

    # -----------------------------------------------------
    # KPI
    # -----------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Products", len(products))

    with col2:
        st.metric("Active Leads", total_leads)

    with col3:
        st.metric(
            "Price Review",
            f"{rules.get('price_review_days', 15)} days",
        )

    with col4:
        st.metric(
            "Today",
            date.today().strftime("%d %b"),
        )

    st.markdown("<hr>", unsafe_allow_html=True)

    # -----------------------------------------------------
    # PRODUCT CATALOGUE — Spotify-style card grid
    # -----------------------------------------------------

    st.markdown('<p class="section-head">Product Catalogue</p>', unsafe_allow_html=True)

    # Accent colours for each product card (cycling through warm shades)
    card_gradients = [
        "linear-gradient(135deg, #7C1D3D 0%, #E11D48 100%)",
        "linear-gradient(135deg, #92400E 0%, #D97706 100%)",
        "linear-gradient(135deg, #6B21A8 0%, #A855F7 100%)",
        "linear-gradient(135deg, #0F766E 0%, #2DD4BF 100%)",
        "linear-gradient(135deg, #1E3A5F 0%, #38BDF8 100%)",
    ]

    # Render in a responsive grid (3 columns)
    card_cols = st.columns(3)
    for i, product in enumerate(products):
        with card_cols[i % 3]:
            current_price = get_current_price(product["id"])
            grad = card_gradients[i % len(card_gradients)]

            st.markdown(f"""
            <div style="
                background: #181818;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
                padding: 0;
                overflow: hidden;
                transition: transform 0.2s ease, background 0.2s ease;
                margin-bottom: 16px;
            ">
                <div style="
                    height: 140px;
                    background: {grad};
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    position: relative;
                ">
                    <span style="
                        font-size: 52px;
                        font-weight: 900;
                        color: rgba(255,255,255,0.25);
                        letter-spacing: -0.05em;
                        user-select: none;
                    ">{product['name'][0]}</span>
                    <div style="
                        position: absolute;
                        bottom: 12px;
                        right: 14px;
                        width: 40px;
                        height: 40px;
                        border-radius: 50%;
                        background: #E11D48;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
                        opacity: 0;
                        transition: opacity 0.2s;
                    ">
                        <span style="font-size: 16px;">&#9654;</span>
                    </div>
                </div>
                <div style="padding: 16px 18px 18px;">
                    <div style="
                        font-size: 16px;
                        font-weight: 800;
                        color: #FFFFFF;
                        letter-spacing: -0.02em;
                        margin-bottom: 6px;
                    ">{product['name']}</div>
                    <div style="
                        font-size: 12px;
                        color: #B3B3B3;
                        font-weight: 500;
                        margin-bottom: 12px;
                    ">{product.get('spiciness', '—')} · {product.get('colour', '—')} · SHU {product.get('shu', '—')}</div>
                    <div style="
                        font-size: 13px;
                        font-weight: 700;
                        color: {'#E11D48' if current_price else '#B3B3B3'};
                    ">{"₹" + f"{current_price['selling_price']:,.2f}/kg" if current_price else "Not priced yet"}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown('<p class="section-head">Business Reminders</p>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.info(
            "Review market prices regularly. "
            "New market prices should be saved rather "
            "than overwriting historical prices."
        )

    with col2:
        st.warning(
            "Export enquiries require separate pricing "
            "and manual confirmation."
        )

# =========================================================
# PRODUCTS
# =========================================================

elif page == "Products":

    st.title("Product Catalogue")

    st.caption(
        "Your red chilli powder varieties and specifications."
    )

    search = st.text_input(
        "Search products",
        placeholder="Search by variety...",
    )

    filtered_products = products

    if search:

        filtered_products = [
            product
            for product in products
            if search.lower()
            in product["name"].lower()
        ]

    st.write(
        f"Showing **{len(filtered_products)}** products"
    )

    for product in filtered_products:

        current_price = get_current_price(
            product["id"]
        )

        with st.expander(
            product["name"],
            expanded=False,
        ):

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "Colour",
                product.get("colour", "N/A"),
            )

            c2.metric(
                "Spiciness",
                product.get("spiciness", "N/A"),
            )

            c3.metric(
                "SHU",
                product.get("shu", "N/A"),
            )

            c4.metric(
                "ASTA",
                product.get("asta", "N/A"),
            )

            st.divider()

            if current_price:

                st.success(
                    f"Current selling price: "
                    f"₹{current_price['selling_price']:,.2f}/kg"
                )

                st.caption(
                    f"Last verified: "
                    f"{current_price['verified_on']}"
                )

            else:

                st.warning(
                    "No active price has been saved yet."
                )

# =========================================================
# UPDATE PRICES
# =========================================================

elif page == "Update Prices":

    st.title("Update Market Prices")

    st.caption(
        "Update market costs and save a new active selling price."
    )

    if not products:

        st.error("No products found.")

    else:

        selected_name = st.selectbox(
            "Product",
            [p["name"] for p in products],
        )

        selected = next(
            p for p in products
            if p["name"] == selected_name
        )

        # -------------------------------------------------
        # EXISTING PRICE
        # -------------------------------------------------

        existing_price = get_current_price(
            selected["id"]
        )

        if existing_price:

            st.info(
                f"Current saved selling price: "
                f"₹{existing_price['selling_price']:,.2f}/kg"
            )

        else:

            st.info(
                "No current price saved for this product."
            )

        st.divider()

        left, right = st.columns(2)

        # -------------------------------------------------
        # COSTS
        # -------------------------------------------------

        with left:

            st.subheader("Cost Structure")

            market_cost = st.number_input(
                "Market/raw material cost (₹/kg)",
                min_value=0.0,
                value=0.0,
                step=1.0,
            )

            processing_cost = st.number_input(
                "Processing cost (₹/kg)",
                min_value=0.0,
                value=0.0,
                step=1.0,
            )

            packaging_cost = st.number_input(
                "Packaging cost (₹/kg)",
                min_value=0.0,
                value=0.0,
                step=1.0,
            )

            other_cost = st.number_input(
                "Other costs (₹/kg)",
                min_value=0.0,
                value=0.0,
                step=1.0,
            )

        # -------------------------------------------------
        # PRICING
        # -------------------------------------------------

        with right:

            st.subheader("Pricing Strategy")

            margin = st.number_input(
                "Target margin (%)",
                min_value=0.0,
                max_value=100.0,
                value=10.0,
                step=0.5,
            )

            effective_date = st.date_input(
                "Effective from",
                value=date.today(),
            )

            price_type = st.selectbox(
                "Price type",
                [
                    "Domestic",
                    "Export",
                ],
            )

            source = st.text_input(
                "Price source",
                placeholder="Supplier / Market / Manual",
            )

        # -------------------------------------------------
        # CALCULATION
        # -------------------------------------------------

        total_cost = (
            market_cost
            + processing_cost
            + packaging_cost
            + other_cost
        )

        selling_price = (
            total_cost
            * (1 + margin / 100)
        )

        st.divider()

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Total Cost",
            f"₹{total_cost:,.2f}/kg",
        )

        c2.metric(
            "Margin",
            f"{margin:.1f}%",
        )

        c3.metric(
            "Recommended Price",
            f"₹{selling_price:,.2f}/kg",
        )

        if price_type == "Export":

            st.warning(
                "Export pricing selected. "
                "Final price must be manually confirmed."
            )

        # -------------------------------------------------
        # SAVE
        # -------------------------------------------------

        if st.button(
            "Calculate & Save Price",
            type="primary",
            use_container_width=True,
        ):

            if market_cost <= 0:

                st.error(
                    "Please enter a valid market/raw material cost."
                )

            else:

                save_price(
                    product_id=selected["id"],
                    market_cost=market_cost,
                    processing_cost=processing_cost,
                    packaging_cost=packaging_cost,
                    other_cost=other_cost,
                    margin_percent=margin,
                    selling_price=selling_price,
                    price_type=price_type,
                    source=source or "Manual",
                    effective_from=effective_date.strftime(
                        "%Y-%m-%d"
                    ),
                )

                st.success(
                    f"{selected_name} price saved successfully!"
                )

                st.metric(
                    "Active Selling Price",
                    f"₹{selling_price:,.2f}/kg",
                )

                if price_type == "Export":

                    st.warning(
                        "Export price saved. "
                        "Manual confirmation is required."
                    )

# =========================================================
# LEADS
# =========================================================

elif page == "Leads":

    st.title("IndiaMART Leads")

    st.caption(
        "Customer enquiries, follow-ups and quotation tracking."
    )

    # Use DB leads (primary) merged with legacy JSON leads
    db_leads = get_all_leads()

    # Normalize JSON-style leads (old format) to look like DB leads
    normalized_json_leads = []
    for old in leads:
        # Skip if already exists in DB
        if any(dl.get("customer") == old.get("customer") and dl.get("location") == old.get("place") for dl in db_leads):
            continue
        normalized_json_leads.append({
            "id": f"json_{len(normalized_json_leads)}",
            "customer": old.get("customer", "Unknown"),
            "location": old.get("place", ""),
            "quantity_kg": old.get("quantity"),
            "requirement": old.get("remarks", ""),
            "delivery_address": old.get("delivery_address"),
            "created_at": old.get("date"),
            "status": old.get("status", "New"),
            "next_follow_up": old.get("follow_up"),
            "is_parsed": 0,
        })

    all_leads_combined = db_leads + normalized_json_leads

    if not all_leads_combined:

        st.info("No leads have been added yet.")

    else:

        # -------------------------------------------------
        # LEAD SUMMARY
        # -------------------------------------------------

        total_leads = len(all_leads_combined)

        new_leads = sum(
            1
            for lead in all_leads_combined
            if str(lead.get("status", "New")).lower() == "new"
        )

        quoted_leads = sum(
            1
            for lead in all_leads_combined
            if str(lead.get("status", "")).lower() == "quoted"
        )

        won_leads = sum(
            1
            for lead in all_leads_combined
            if str(lead.get("status", "")).lower() == "converted"
        )

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Total Leads", total_leads)

        with c2:
            st.metric("New", new_leads)

        with c3:
            st.metric("Quoted", quoted_leads)

        with c4:
            st.metric("Converted", won_leads)

        st.divider()

        # -------------------------------------------------
        # SEARCH
        # -------------------------------------------------

        search = st.text_input(
            "Search leads",
            placeholder="Search by customer, location or requirement...",
        )

        filter_col1, _ = st.columns([1, 3])

        with filter_col1:
            status_filter = st.selectbox(
                "Filter by Status",
                [
                    "All",
                    "New",
                    "Follow-up",
                    "Quoted",
                    "Converted",
                    "Lost",
                ],
                key="lead_status_filter",
            )

        filtered_leads = all_leads_combined

        # Status filter
        if status_filter != "All":
            filtered_leads = [
                lead
                for lead in filtered_leads
                if str(
                    lead.get("status") or "New"
                ).strip().lower() == status_filter.lower()
            ]

        # Search filter
        if search.strip():
            search_text = search.lower().strip()

            filtered_leads = [
                lead
                for lead in filtered_leads
                if search_text in str(
                    lead.get("customer") or ""
                ).lower()
                or search_text in str(
                    lead.get("location") or ""
                ).lower()
                or search_text in str(
                    lead.get("requirement") or ""
                ).lower()
                or search_text in str(
                    lead.get("delivery_address") or ""
                ).lower()
            ]

        st.write(
            f"**{len(filtered_leads)} lead(s) found**"
        )

        # -------------------------------------------------
        # LEAD CARDS
        # -------------------------------------------------

        for index, lead in enumerate(filtered_leads):

            customer = (
                str(lead.get("customer") or "Unknown Customer")
                .strip()
            )

            location = (
                str(lead.get("location") or "Location not provided")
                .strip()
            )

            # Quantity — normalize for display
            qty_value = parse_quantity(lead.get("quantity_kg"))
            if qty_value is not None:
                quantity = f"{qty_value:,.0f} kg"
            else:
                quantity = "Not Specified"

            enquiry_date = (
                str(lead.get("created_at") or "Date not available")
                .strip()
            )

            remarks = (
                str(lead.get("requirement") or lead.get("remarks") or "")
                .strip()
            )

            address = (
                str(lead.get("delivery_address") or "")
                .strip()
            )

            status = (
                str(lead.get("status") or "New")
                .strip()
            )

            follow_up = (
                str(lead.get("next_follow_up") or lead.get("follow_up") or "Not scheduled")
                .strip()
            )

            with st.container(border=True):

                # -------------------------------------------------
                # HEADER
                # -------------------------------------------------

                col1, col2 = st.columns([3.5, 1])

                with col1:
                    st.subheader(customer)

                    st.caption(
                        f"Location: {location}"
                    )

                with col2:
                    st.write("**Status**")

                    statuses = ["New", "Follow-up", "Quoted", "Converted", "Lost"]
                    new_status = st.selectbox(
                        "Status",
                        statuses,
                        index=(
                            statuses.index(status)
                            if status in statuses
                            else 0
                        ),
                        key=f"lead_status_{index}_{lead.get('id', index)}",
                        label_visibility="collapsed",
                    )

                st.divider()

                # -------------------------------------------------
                # LEAD DETAILS
                # -------------------------------------------------

                c1, c2, c3 = st.columns(3)

                with c1:
                    st.write("**Quantity**")
                    st.write(quantity)

                with c2:
                    st.write("**Enquiry Date**")
                    st.write(enquiry_date)

                with c3:
                    st.write("**Follow-up**")
                    st.write(follow_up)

                # Parsed fields
                if lead.get("parsed_variety"):
                    st.caption(f"Detected variety: {lead.get('parsed_variety')}")
                if lead.get("parsed_quantity") and not lead.get("quantity_kg"):
                    st.caption(f"Detected qty: {lead.get('parsed_quantity'):,.0f} kg")

                # -------------------------------------------------
                # REQUIREMENT
                # -------------------------------------------------

                if remarks:
                    st.write(
                        f"**Requirement:** {remarks}"
                    )

                # -------------------------------------------------
                # DELIVERY ADDRESS
                # -------------------------------------------------

                if address:
                    st.caption(
                        f"Delivery: {address}"
                    )

                # -------------------------------------------------
                # UPDATE STATUS (DB leads only)
                # -------------------------------------------------

                if new_status != status and not str(lead.get("id", "")).startswith("json_"):
                    next_follow_up = calculate_next_follow_up(new_status)
                    update_lead_status(lead["id"], new_status, next_follow_up)
                    st.success(f"Status updated to {new_status}.")
                    st.rerun()
# ============================================================
# CUSTOMER MANAGEMENT
# ============================================================

if page == "Customers":

    st.title("Customer Management")
    st.caption("Manage customer records, contacts and sales information.")

    # -----------------------------
    # ADD CUSTOMER
    # -----------------------------
    with st.expander("+ Add New Customer", expanded=False):

        col1, col2 = st.columns(2)

        with col1:
            customer_name = st.text_input(
                "Customer / Company Name",
                key="customer_name"
            )

            contact_person = st.text_input(
                "Contact Person",
                key="contact_person"
            )

            phone = st.text_input(
                "Phone Number",
                key="customer_phone"
            )

            email = st.text_input(
                "Email",
                key="customer_email"
            )

        with col2:
            location = st.text_input(
                "Location",
                key="customer_location"
            )

            address = st.text_area(
                "Address",
                key="customer_address"
            )

            product_interest = st.text_input(
                "Product Interest",
                key="customer_product"
            )

            status = st.selectbox(
                "Customer Status",
                ["Active", "Potential", "Inactive"],
                key="customer_status"
            )

        notes = st.text_area(
            "Notes",
            key="customer_notes"
        )

        if st.button("Save Customer", type="primary"):

            if not customer_name.strip():
                st.error("Customer / Company Name is required.")

            else:
                new_customer = {
                    "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                    "customer": customer_name.strip(),
                    "contact_person": contact_person.strip(),
                    "phone": phone.strip(),
                    "email": email.strip(),
                    "location": location.strip(),
                    "address": address.strip(),
                    "product_interest": product_interest.strip(),
                    "status": status,
                    "notes": notes.strip(),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                customers.append(new_customer)

                with open(
                    CUSTOMERS_FILE,
                    "w",
                    encoding="utf-8"
                ) as file:
                    json.dump(
                        customers,
                        file,
                        indent=4,
                        ensure_ascii=False
                    )

                st.success("Customer added successfully.")
                st.rerun()

    st.divider()

    # -----------------------------
    # CUSTOMER SEARCH
    # -----------------------------

    st.subheader("Customers")

    search = st.text_input(
        "Search customers",
        placeholder="Search by company, contact person, phone or location..."
    )

    filtered_customers = customers

    if search.strip():
        search_text = search.lower().strip()

        filtered_customers = [
            customer
            for customer in customers
            if search_text in str(customer.get("customer", "")).lower()
            or search_text in str(customer.get("contact_person", "")).lower()
            or search_text in str(customer.get("phone", "")).lower()
            or search_text in str(customer.get("location", "")).lower()
        ]

    # -----------------------------
    # CUSTOMER LIST
    # -----------------------------

    if not filtered_customers:

        st.info("No customers found.")

    else:

        st.write(
            f"**{len(filtered_customers)} customer(s) found**"
        )

        for customer in filtered_customers:

            with st.container(border=True):

                col1, col2, col3 = st.columns([2.5, 1.5, 1])

                with col1:

                    st.subheader(
                        customer.get(
                            "customer",
                            "Unknown Customer"
                        )
                    )

                    if customer.get("contact_person"):
                        st.caption(
                            f"Contact: {customer['contact_person']}"
                        )

                    if customer.get("location"):
                        st.caption(
                            f"Location: {customer['location']}"
                        )

                with col2:

                    if customer.get("phone"):
                        st.write(
                            f"Phone: {customer['phone']}"
                        )

                    if customer.get("email"):
                        st.write(
                            f"Email: {customer['email']}"
                        )

                with col3:

                    st.write(
                        f"**{customer.get('status', 'Active')}**"
                    )

                    if customer.get("product_interest"):
                        st.caption(
                            customer["product_interest"]
                        )

                if customer.get("address"):
                    st.caption(
                        f"Address: {customer['address']}"
                    )

                if customer.get("notes"):
                    st.caption(
                        f"Notes: {customer['notes']}"
                    )

# =========================================================
# ENQUIRIES
# =========================================================

elif page == "Enquiries":

    if HAS_ENQUIRY_INGEST:
        render_enquiries_page()
    else:
        st.error("Could not load Enquiries module. Check app/enquiry_ingest.py.")

# =========================================================
# PRICING TIERS
# =========================================================

elif page == "Pricing Tiers":

    st.title("Pricing Tiers")
    st.caption("Define quantity-based price tiers per variety.")

    all_products = products

    for prod in all_products:

        product_id = prod["id"]
        product_name = prod["name"]
        tiers = get_tiers_for_product(product_id)

        with st.expander(f"{product_name}", expanded=False):

            if tiers:
                # Show existing tiers
                for tier in tiers:
                    col_t1, col_t2, col_t3, col_t4 = st.columns([1, 1, 1, 1])
                    col_t1.write(f"**Min:** {tier.get('min_qty', 0):,.0f} kg")
                    col_t2.write(f"**Max:** {tier.get('max_qty', '∞')} kg")
                    col_t3.write(f"**Rate:** ₹{tier.get('rate_per_kg', 0):,.2f}/kg")
                    if col_t4.button("Delete", key=f"del_tier_{product_id}_{tier['min_qty']}"):
                        remove_tier(product_id, tier["min_qty"])
                        st.rerun()

            st.divider()

            # Add new tier
            st.write("Add a new tier:")
            c_min, c_max, c_rate, c_add = st.columns([1, 1, 1, 1])
            min_qty = c_min.number_input("Min qty (kg)", min_value=1.0, value=1.0, step=10.0, key=f"min_{product_id}")
            max_qty_raw = c_max.number_input("Max qty (kg) — leave empty for ∞", min_value=0.0, value=100.0, step=10.0, key=f"max_{product_id}")
            max_qty = None if max_qty_raw == 0 else max_qty_raw
            rate = c_rate.number_input("Rate (₹/kg)", min_value=0.0, value=100.0, step=1.0, key=f"rate_{product_id}")
            if c_add.button("Add Tier", key=f"add_tier_{product_id}"):
                add_tier(product_id, min_qty, max_qty, rate)
                st.success(f"Tier added for {product_name}.")
                st.rerun()

# =========================================================
# FOLLOW-UPS
# =========================================================

elif page == "Follow-ups":

    st.title("Follow-ups")
    st.caption("Track and manage customer follow-ups.")

    all_leads = get_all_leads()
    today = date.today().strftime("%Y-%m-%d")

    overdue = get_overdue_leads(all_leads)
    due_today = get_due_today_leads(all_leads)
    upcoming = get_upcoming_leads(all_leads, days=7)

    col_o, col_t, col_u = st.columns(3)
    col_o.metric("Overdue", len(overdue))
    col_t.metric("Due Today", len(due_today))
    col_u.metric("Upcoming (7 days)", len(upcoming))

    st.divider()

    tab_overdue, tab_today, tab_upcoming = st.tabs(
        [f"Overdue ({len(overdue)})", f"Due Today ({len(due_today)})", f"Upcoming ({len(upcoming)})"]
    )

    def _render_lead_card(lead: dict, show_schedule: bool = True):
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            col1.subheader(lead.get("customer", "Unknown"))
            col1.caption(f"Location: {lead.get('location', 'N/A')}  •  Status: **{lead.get('status', 'New')}**")
            col1.caption(f"Next follow-up: **{lead.get('next_follow_up', 'Not set')}**")
            col1.caption(f"Variety: {lead.get('parsed_variety') or '—'}  •  Qty: {lead.get('parsed_quantity') or '—'} kg")

            if show_schedule:
                new_date = col2.date_input(
                    "Reschedule to",
                    value=date.today(),
                    key=f"followup_date_{lead['id']}",
                )
                if col2.button("Update", key=f"update_followup_{lead['id']}"):
                    update_lead_status(lead["id"], lead.get("status", "Follow-up"), new_date.strftime("%Y-%m-%d"))
                    st.success("Follow-up date updated.")
                    st.rerun()

            if col1.button("Mark as Contacted", key=f"contacted_{lead['id']}"):
                next_date = calculate_next_follow_up(lead.get("status", "Follow-up"))
                update_lead_status(lead["id"], lead.get("status", "Follow-up"), next_date)
                st.success("Marked as contacted. Next follow-up scheduled.")
                st.rerun()

    with tab_overdue:
        if overdue:
            for lead in overdue:
                _render_lead_card(lead)
        else:
            st.success("No overdue follow-ups!")

    with tab_today:
        if due_today:
            for lead in due_today:
                _render_lead_card(lead)
        else:
            st.info("No follow-ups due today.")

    with tab_upcoming:
        if upcoming:
            for lead in upcoming:
                _render_lead_card(lead, show_schedule=False)
        else:
            st.info("No upcoming follow-ups in the next 7 days.")

# =========================================================
# USER MANAGEMENT (Admin only)
# =========================================================

elif page == "User Management":

    if current_user.get("role") != "admin":
        st.error("You do not have permission to view this page.")
        st.stop()

    st.title("User Management")
    st.caption("Add, remove, and manage users (admin only).")

    # -------------------------------------------------
    # ADD USER
    # -------------------------------------------------
    with st.expander("+ Add New User", expanded=False):

        col1, col2 = st.columns(2)

        with col1:
            new_username = st.text_input("Username", key="new_user_username")
            new_password = st.text_input("Password", type="password", key="new_user_password")
            confirm_password = st.text_input("Confirm password", type="password", key="new_user_confirm")

        with col2:
            new_full_name = st.text_input("Full name", key="new_user_fullname")
            new_role = st.selectbox("Role", ["user", "admin"], key="new_user_role")

        if st.button("Add User", type="primary", key="add_user_btn"):
            if not new_username.strip():
                st.error("Username is required.")
            elif not new_password.strip():
                st.error("Password is required.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            elif len(new_password) < 4:
                st.error("Password must be at least 4 characters.")
            else:
                success = add_user(
                    new_username.strip(),
                    new_password,
                    role=new_role,
                    full_name=new_full_name.strip(),
                )
                if success:
                    st.success(f"User '{new_username}' added successfully.")
                    st.rerun()
                else:
                    st.error(f"Username '{new_username}' already exists.")

    st.divider()

    # -------------------------------------------------
    # USER LIST
    # -------------------------------------------------
    st.subheader("Users")

    current_users = users_data.get("users", [])

    if not current_users:
        st.info("No users yet.")
    else:
        st.write(f"**{len(current_users)} user(s)**")

        for user in current_users:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

                col1.subheader(user.get("full_name") or user.get("username"))
                col1.caption(f"@{user.get('username')}")
                col2.write(f"**{user.get('role', 'user').title()}**")
                col3.caption(f"Joined: {user.get('created_at', 'N/A')}")

                is_self = user.get("username") == current_user.get("username")
                if not is_self and col4.button("Remove", key=f"del_user_{user.get('username')}"):
                    users_data["users"] = [u for u in current_users if u.get("username") != user.get("username")]
                    save_json(USERS_FILE, users_data)
                    USERS.pop(user.get("username"), None)
                    st.success(f"User '{user.get('username')}' removed.")
                    st.rerun()

# =========================================================
# QUOTATION
# =========================================================

elif page == "Quotation":

    st.title("Quotation")
    st.caption("Create and send a quotation. Rate is auto-filled based on quantity tiers.")

    # Lazy-load the quotation sender (only when needed)
    try:
        from services.quotation_sender import send_quotation
        from services.email_sender import is_email_configured
        from services.whatsapp_sender import is_whatsapp_configured
        HAS_QUOTATION_SENDER = True
    except Exception:
        HAS_QUOTATION_SENDER = False

    # ---- LEAD SELECTOR ----
    all_leads = get_all_leads()
    lead_options = [
        {"label": f"{l.get('customer', 'Unknown')} — {l.get('location', '')}", "lead": l}
        for l in all_leads
    ]

    use_lead = st.checkbox("Create quotation for existing lead")

    selected_lead = None
    if use_lead:
        if not lead_options:
            st.info("No leads in the database yet. Add leads via Enquiries or Leads page.")
        else:
            selected_idx = st.selectbox(
                "Select lead",
                range(len(lead_options)),
                format_func=lambda i: lead_options[i]["label"],
            )
            selected_lead = lead_options[selected_idx]["lead"]

    # ---- QUOTATION FIELDS ----
    col_left, col_right = st.columns(2)

    with col_left:
        customer = st.text_input(
            "Customer / Company",
            value=selected_lead.get("customer", "") if selected_lead else "",
        )
        location = st.text_input(
            "Location",
            value=selected_lead.get("location", "") if selected_lead else "",
        )

    with col_right:
        product_names = [p["name"] for p in products]
        default_product = ""
        if selected_lead and selected_lead.get("parsed_variety"):
            matched = [n for n in product_names if selected_lead["parsed_variety"].lower() in n.lower()]
            if matched:
                default_product = matched[0]

        selected_name = st.selectbox(
            "Product",
            product_names,
            index=product_names.index(default_product) if default_product in product_names else 0,
        )
        selected = next(p for p in products if p["name"] == selected_name)

    quantity = st.number_input(
        "Quantity (kg)",
        min_value=1.0,
        value=parse_quantity(selected_lead.get("parsed_quantity"), 100.0) if selected_lead else 100.0,
        step=50.0,
    )

    # ---- TIERED PRICING ----
    tiers = get_tiers_for_product(selected["id"])
    tier_rate = None
    if tiers:
        for tier in tiers:
            min_qty = tier.get("min_qty", 0)
            max_qty = tier.get("max_qty")
            if max_qty is None or quantity <= max_qty:
                tier_rate = tier["rate_per_kg"]
                tier_label = (
                    f"₹{tier_rate:,.2f}/kg "
                    f"({tier['min_qty']:,.0f}"
                    + (f"–{tier['max_qty']:,.0f}" if tier.get("max_qty") else "+")
                    + " kg)"
                )
                st.info(f"Tier rate applied: **{tier_label}**")
                break
        if tier_rate is None:
            tier_rate = tiers[-1]["rate_per_kg"]
            st.info(f"Using highest-tier rate: **₹{tier_rate:,.2f}/kg** (500+ kg)")
    else:
        current_price = get_current_price(selected["id"])
        if current_price:
            tier_rate = float(current_price["selling_price"])
            st.info(f"No tiers defined — using saved price: **₹{tier_rate:,.2f}/kg**")
        else:
            st.warning("No tiers or saved price. Enter price manually.")
            tier_rate = 0.0

    price = st.number_input(
        "Quoted price (₹/kg)",
        min_value=0.0,
        value=tier_rate if tier_rate else 0.0,
        step=1.0,
    )

    packaging = st.text_input(
        "Packaging",
        placeholder="e.g. 25 kg bags",
        value="25 kg bags",
    )

    total = quantity * price

    st.divider()

    c1, c2, c3 = st.columns(3)
    c1.metric("Quantity", f"{quantity:,.0f} kg")
    c2.metric("Rate", f"₹{price:,.2f}/kg")
    c3.metric("Total Value", f"₹{total:,.2f}")

    quotation_pdf = build_quotation_pdf(
        customer=customer,
        location=location,
        product=selected_name,
        quantity=quantity,
        price=price,
        packaging=packaging,
        quotation_date=date.today().strftime("%d-%m-%Y"),
    )

    safe_customer = "".join(
        ch if ch.isalnum() or ch in (" ", "-", "_") else "_"
        for ch in customer
    ).strip().replace(" ", "_")

    pdf_filename = (
        f"Quotation_{safe_customer or 'Customer'}_"
        f"{date.today().strftime('%Y%m%d')}.pdf"
    )

    st.download_button(
        "Download PDF",
        data=quotation_pdf,
        file_name=pdf_filename,
        mime="application/pdf",
        use_container_width=True,
    )

    st.divider()

    # ---- SEND SECTION ----
    st.subheader("Send to Customer")

    send_channels = []
    if HAS_QUOTATION_SENDER:
        if is_email_configured():
            send_channels.append("Email")
        if is_whatsapp_configured():
            send_channels.append("WhatsApp")

    if not customer or not price:
        st.info("Fill in customer name and price to enable sending.")
    else:
        channel = st.selectbox(
            "Send via",
            send_channels if send_channels else ["(configure in secrets.json)"],
        ) if send_channels else st.selectbox("Send via", ["(configure in secrets.json)"])

        confirm = st.checkbox(
            f"I confirm the quotation details are correct and want to send it via {channel}.",
            value=False,
        )

        if st.button(
            f"Confirm & Send via {channel}",
            type="primary",
            use_container_width=True,
            disabled=not confirm,
        ):
            lead_for_send = selected_lead or {}
            lead_for_send["customer"] = customer
            lead_for_send["location"] = location
            lead_for_send["product_id"] = selected["id"]

            result = send_quotation(
                lead=lead_for_send,
                product_name=selected_name,
                quantity=quantity,
                rate_per_kg=price,
                pdf_bytes=quotation_pdf,
                channel=channel.lower() if channel != "(configure in secrets.json)" else "email",
            )

            if result.get("success"):
                st.success(f"Quotation sent via {result.get('channel', channel)}!")
                if selected_lead:
                    next_follow_up = calculate_next_follow_up("Quoted")
                    update_lead_status(selected_lead["id"], "Quoted", next_follow_up)
                    st.rerun()
            else:
                st.error(f"Send failed: {result.get('error', 'Unknown error')}")

    st.divider()

    # ---- QUOTATION HISTORY ----
    st.subheader("Quotation History")

    history = get_quotation_history()
    if history:
        for q in history[:10]:
            with st.container(border=True):
                col_a, col_b, col_c = st.columns(3)
                col_a.write(f"**{q.get('customer', 'N/A')}**")
                col_a.caption(f"{q.get('quotation_no', '')}")
                col_b.write(f"{q.get('quantity_kg', 0):,.0f} kg × ₹{q.get('rate_per_kg', 0):,.2f}")
                col_b.caption(f"Total: ₹{q.get('total_value', 0):,.2f}")
                col_c.write(f"**{q.get('channel', '').upper()}**")
                col_c.caption(f"{q.get('sent_at', '')}")
    else:
        st.info("No quotations sent yet.")