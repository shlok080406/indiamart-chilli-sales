"""Minimal test to check if login flow works."""
import streamlit as st

st.set_page_config(page_title="Test", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.markdown("### Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Sign In"):
        if u == "admin" and p == "7844":
            st.session_state["logged_in"] = True
            st.rerun()
        else:
            st.error("Wrong")
    st.stop()

st.markdown("### Dashboard")
st.success("Logged in!")
