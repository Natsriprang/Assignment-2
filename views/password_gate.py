"""Password gate for the public deployment. The password is never in the code: it is read from the APP_PASSWORD setting, from
the .env file on your own machine or from the app's Secrets on Streamlit Cloud (which it passes on as environment variables).
Until the right password is typed in a browser session, nothing else is drawn."""
import hmac
import os

import streamlit as st
from dotenv import load_dotenv

ENV_NAME = "APP_PASSWORD"
OK_KEY = "password_ok"

load_dotenv()


def require_password():
    """Returns when this session has typed the right password; otherwise draws the password box and stops the script."""
    if st.session_state.get(OK_KEY):
        return
    st.title("Contract Drafting Assistant")
    expected = os.getenv(ENV_NAME, "")
    if not expected:
        st.error(f"No password is set for this app. Add {ENV_NAME} to the .env file (or to the app's Secrets on Streamlit Cloud).")
        st.stop()
    entered = st.text_input("Password", type="password", key="gate_password")
    if entered:
        if hmac.compare_digest(entered.encode(), expected.encode()):
            st.session_state[OK_KEY] = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()
