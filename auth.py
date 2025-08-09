import streamlit as st
from database import get_user

def login():
    st.subheader("🔑 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = get_user(username, password)
        if user:
            st.session_state["user"] = {"id": user[0], "name": user[1]}
            st.success(f"Welcome {user[1]} 👋")
            st.experimental_rerun()
        else:
            st.error("Invalid credentials")
