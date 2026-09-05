"""
Enquiry ingest page for the Streamlit dashboard.

Renders the "Enquiries" page that:
- Pulls new enquiries from IndiaMART API
- Shows raw text + AI-parsed fields
- Lets the user confirm and convert into a lead
"""

import streamlit as st
from datetime import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.indiamart_api import (
    fetch_enquiries,
    is_configured as indiamart_configured,
)
from services.enquiry_parser import parse_enquiry
from database.pricing_db import (
    insert_lead,
    get_unread_leads,
)


def render_enquiries_page():
    """Render the Enquiries page in the Streamlit dashboard."""

    st.title("IndiaMART Enquiries")
    st.caption("Pull enquiries from IndiaMART, parse them with AI, and add as leads.")

    if not indiamart_configured():
        st.warning(
            "IndiaMART API credentials are not configured. "
            "Add `indiamart_crm_id` and `indiamart_api_key` to "
            "`data/secrets.json` or set them as environment variables."
        )
        st.info(
            "You can still paste enquiry text manually below to test the AI parser."
        )

    st.divider()

    # -----------------------------------------------------
    # SECTION 1: MANUAL ENTRY (works without API keys)
    # -----------------------------------------------------

    st.subheader("Manual Enquiry Entry")

    with st.form("manual_enquiry_form", clear_on_submit=True):
        raw_text = st.text_area(
            "Enquiry text",
            placeholder=(
                "e.g. 'Hi, I am Rajesh from Mumbai. I need 500 kg of Teja "
                "chilli powder. Please share your best price. Contact: 9876543210'"
            ),
            height=120,
        )

        submitted = st.form_submit_button(
            "Parse & Add as Lead", type="primary"
        )

        if submitted and raw_text.strip():
            parsed = parse_enquiry(raw_text)
            parsed["enquiry_raw_text"] = raw_text
            parsed["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            parsed["status"] = "New"
            parsed["is_parsed"] = 1 if parsed.get("parsed_quantity") or parsed.get("parsed_variety") else 0

            if not parsed.get("customer"):
                parsed["customer"] = "Unknown Customer"

            lead_id = insert_lead(parsed)
            st.success(f"Lead #{lead_id} created successfully!")

            if parsed:
                with st.expander("Parsed fields", expanded=True):
                    st.json(parsed)

    st.divider()

    # -----------------------------------------------------
    # SECTION 1B: BULK / CSV IMPORT (no API needed)
    # -----------------------------------------------------

    st.subheader("Bulk Import (no API required)")
    st.caption(
        "IndiaMART Pull API is a paid add-on. Use these free alternatives: "
        "export leads from the IndiaMART 'Import Leads' tab, or paste them here."
    )

    tab_csv, tab_paste = st.tabs(["Upload CSV/Excel", "Bulk Paste"])

    with tab_csv:
        st.caption(
            "Expected columns: `customer` (or `name`), `phone` (or `mobile`), "
            "`email`, `city` (or `location`), `message` (or `enquiry`, `query`). "
            "Other columns are ignored."
        )
        uploaded = st.file_uploader(
            "Upload CSV or Excel file",
            type=["csv", "xlsx", "xls"],
            key="bulk_csv_upload",
        )
        if uploaded is not None:
            try:
                if uploaded.name.lower().endswith(".csv"):
                    import pandas as pd
                    df = pd.read_csv(uploaded)
                else:
                    import pandas as pd
                    df = pd.read_excel(uploaded)
            except Exception as e:
                st.error(f"Could not read file: {e}")
                df = None

            if df is not None and not df.empty:
                st.write(f"Found **{len(df)}** rows. Preview:")
                st.dataframe(df.head(10), use_container_width=True)

                # Map common column-name variants to a canonical name
                col_map = {}
                for col in df.columns:
                    c = str(col).strip().lower()
                    if c in ("customer", "name", "sender_name", "buyer"):
                        col_map[col] = "customer"
                    elif c in ("phone", "mobile", "sender_mobile", "contact"):
                        col_map[col] = "phone"
                    elif c in ("email", "sender_email", "e-mail"):
                        col_map[col] = "email"
                    elif c in ("city", "location", "sender_city", "place"):
                        col_map[col] = "location"
                    elif c in ("message", "enquiry", "query", "query_message",
                               "raw_message", "details"):
                        col_map[col] = "raw_message"
                    elif c in ("company", "sender_company", "organization"):
                        col_map[col] = "company"

                if st.button("Import All as Leads", type="primary",
                             key="import_csv_btn"):
                    imported = 0
                    for _, row in df.iterrows():
                        raw_parts = []
                        for col in df.columns:
                            val = str(row[col]).strip()
                            if val and val.lower() != "nan":
                                raw_parts.append(f"{col}: {val}")
                        raw_text = "\n".join(raw_parts)

                        customer = ""
                        phone = ""
                        email = ""
                        location = ""
                        company = ""
                        for src, dst in col_map.items():
                            val = str(row[src]).strip()
                            if not val or val.lower() == "nan":
                                continue
                            if dst == "customer" and not customer:
                                customer = val
                            elif dst == "phone" and not phone:
                                phone = val
                            elif dst == "email" and not email:
                                email = val
                            elif dst == "location" and not location:
                                location = val
                            elif dst == "company" and not company:
                                company = val

                        parsed = parse_enquiry(raw_text)
                        parsed["enquiry_raw_text"] = raw_text
                        parsed["customer"] = customer or parsed.get("customer") \
                            or "Unknown Customer"
                        if phone:
                            parsed["phone"] = phone
                        if email:
                            parsed["email"] = email
                        if location:
                            parsed["location"] = location
                        if company:
                            parsed["company"] = company
                        parsed["source"] = "csv_import"
                        parsed["created_at"] = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S")
                        parsed["status"] = "New"
                        parsed["is_parsed"] = 1 if (
                            parsed.get("parsed_quantity")
                            or parsed.get("parsed_variety")
                        ) else 0

                        insert_lead(parsed)
                        imported += 1

                    st.success(f"Imported {imported} leads from file.")

    with tab_paste:
        st.caption(
            "Paste multiple enquiries separated by a blank line. Each block "
            "becomes one lead."
        )
        bulk_text = st.text_area(
            "Paste enquiries (separate each with a blank line)",
            height=200,
            key="bulk_paste_text",
        )
        if st.button("Parse & Add All as Leads", type="primary",
                     key="bulk_paste_btn"):
            if not bulk_text.strip():
                st.warning("Paste at least one enquiry first.")
            else:
                blocks = [b.strip() for b in bulk_text.split("\n\n") if b.strip()]
                imported = 0
                for block in blocks:
                    parsed = parse_enquiry(block)
                    parsed["enquiry_raw_text"] = block
                    parsed["customer"] = parsed.get("customer") or "Unknown Customer"
                    parsed["source"] = "bulk_paste"
                    parsed["created_at"] = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S")
                    parsed["status"] = "New"
                    parsed["is_parsed"] = 1 if (
                        parsed.get("parsed_quantity")
                        or parsed.get("parsed_variety")
                    ) else 0
                    insert_lead(parsed)
                    imported += 1
                st.success(f"Imported {imported} leads from pasted text.")

    st.divider()

    # -----------------------------------------------------
    # SECTION 2: SYNC FROM INDIAMART API
    # -----------------------------------------------------

    st.subheader("Sync from IndiaMART")

    if indiamart_configured():
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Pull New Enquiries", type="primary"):
                with st.spinner("Pulling enquiries from IndiaMART..."):
                    enquiries = fetch_enquiries()
                    st.session_state["fetched_enquiries"] = enquiries

        if st.session_state.get("fetched_enquiries"):
            enquiries = st.session_state["fetched_enquiries"]
            st.write(f"**{len(enquiries)}** new enquiries fetched")

            for idx, enquiry in enumerate(enquiries):
                with st.container(border=True):
                    st.markdown(f"### {enquiry.get('customer', 'Unknown')}")
                    st.caption(
                        f"📍 {enquiry.get('location', 'N/A')}  •  "
                        f"📞 {enquiry.get('phone', 'N/A')}"
                    )

                    with st.expander("Raw message", expanded=False):
                        st.text(enquiry.get("raw_message", ""))

                    if st.button(
                        "Parse & Add as Lead",
                        key=f"parse_{idx}_{enquiry.get('enquiry_id', idx)}",
                    ):
                        raw = enquiry.get("raw_message", "")
                        parsed = parse_enquiry(raw)
                        # Carry over IndiaMART-sourced fields
                        parsed["enquiry_raw_text"] = raw
                        parsed["synced_at"] = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if not parsed.get("customer"):
                            parsed["customer"] = enquiry.get("customer", "Unknown")
                        if not parsed.get("phone"):
                            parsed["phone"] = enquiry.get("phone")
                        if not parsed.get("email"):
                            parsed["email"] = enquiry.get("email")
                        if not parsed.get("location"):
                            parsed["location"] = enquiry.get("location")
                        if not parsed.get("company"):
                            parsed["company"] = enquiry.get("company")
                        parsed["created_at"] = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        parsed["status"] = "New"
                        parsed["is_parsed"] = 1

                        lead_id = insert_lead(parsed)
                        st.success(f"Lead #{lead_id} added.")

                        with st.expander("Parsed fields", expanded=False):
                            st.json(parsed)
    else:
        st.info("Set up IndiaMART API credentials to enable auto-sync.")

    st.divider()

    # -----------------------------------------------------
    # SECTION 3: GMAIL WATCHER STATUS (admin only)
    # -----------------------------------------------------

    from services.gmail_watcher import is_configured as gmail_configured, get_status

    user = st.session_state.get("user", {}) or {}
    is_admin = user.get("role") == "admin"

    if is_admin:
        st.subheader("Gmail Watcher (Auto-Import)")
        st.caption(
            "Reads IndiaMART enquiry emails from your Gmail inbox and "
            "auto-creates leads. Run `py run_watcher.py` to start."
        )

        status = get_status()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if gmail_configured():
                st.success("Configured")
            else:
                st.error("Not configured")
        with col2:
            st.metric("Last poll", status.get("last_poll") or "Never")
        with col3:
            st.metric("Leads today", status.get("leads_today", 0))
        with col4:
            st.metric("Processed emails", status.get("processed_count", 0))

        if not gmail_configured():
            st.warning(
                "Add `gmail_user` and `gmail_app_password` to "
                "`data/secrets.json`, or set the `GMAIL_USER` and "
                "`GMAIL_APP_PASSWORD` environment variables, then start the "
                "watcher with: `py run_watcher.py`"
            )
        else:
            with st.expander("How to start the watcher", expanded=False):
                st.code(
                    "py run_watcher.py            # poll every 5 minutes\n"
                    "py run_watcher.py --interval 60    # poll every minute\n"
                    "py run_watcher.py --once     # poll once and exit",
                    language="bash",
                )

    st.divider()

    # -----------------------------------------------------
    # SECTION 4: UNREAD / RECENT LEADS
    # -----------------------------------------------------

    st.subheader("Recent Leads")

    unread = get_unread_leads()
    if unread:
        st.write(f"**{len(unread)}** unprocessed lead(s)")
        for lead in unread[:10]:
            with st.container(border=True):
                st.markdown(
                    f"**{lead.get('customer', 'Unknown')}** "
                    f"— {lead.get('location', 'N/A')}"
                )
                st.caption(
                    f"Variety: {lead.get('parsed_variety') or '—'}  •  "
                    f"Quantity: {lead.get('parsed_quantity') or '—'} kg"
                )
                st.caption(
                    f"Status: {lead.get('status')}  •  "
                    f"Created: {lead.get('created_at')}"
                )
    else:
        st.info("No unprocessed leads.")
