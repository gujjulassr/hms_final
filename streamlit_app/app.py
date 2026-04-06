import streamlit as st
import requests
from views import chat, appointments, profile, doctors, sessions, queue, admin_dashboard

API_URL = "http://localhost:8000"

st.set_page_config(page_title="HMS Chatbot", layout="wide")


# --- Session State Init ---
if "token" not in st.session_state:
    st.session_state.token = None
if "role" not in st.session_state:
    st.session_state.role = None
if "full_name" not in st.session_state:
    st.session_state.full_name = None
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "page" not in st.session_state:
    st.session_state.page = "chat"


def api_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def login(email, password):
    res = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
    if res.status_code == 200:
        data = res.json()
        st.session_state.token = data["token"]
        st.session_state.role = data["role"]
        st.session_state.full_name = data["full_name"]
        return True
    return False


def register(email, password, full_name, phone):
    res = requests.post(f"{API_URL}/api/auth/register", json={
        "email": email, "password": password, "full_name": full_name, "phone": phone
    })
    if res.status_code == 200:
        data = res.json()
        st.session_state.token = data["token"]
        st.session_state.role = data["role"]
        st.session_state.full_name = data["full_name"]
        return True
    return False


def send_message(message):
    body = {"message": message}
    if st.session_state.conversation_id:
        body["conversation_id"] = st.session_state.conversation_id
    res = requests.post(f"{API_URL}/api/chat/message", json=body, headers=api_headers())
    data = res.json()
    st.session_state.conversation_id = data.get("conversation_id")
    return data.get("reply", "Error getting response")


def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def nav(page):
    st.session_state.page = page
    st.rerun()


# ==========================================
# LOGIN PAGE
# ==========================================
if not st.session_state.token:
    st.title("HMS Hospital")
    st.subheader("Login or Register")

    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                if login(email, password):
                    st.rerun()
                else:
                    st.error("Invalid email or password")

    with tab2:
        with st.form("register_form"):
            reg_name = st.text_input("Full Name")
            reg_email = st.text_input("Email")
            reg_phone = st.text_input("Phone")
            reg_pass = st.text_input("Password", type="password")
            if st.form_submit_button("Register"):
                if register(reg_email, reg_pass, reg_name, reg_phone):
                    st.rerun()
                else:
                    st.error("Registration failed")


# ==========================================
# MAIN APP
# ==========================================
else:
    # Sidebar
    with st.sidebar:
        st.write(f"**{st.session_state.full_name}**")
        st.write(f"Role: {st.session_state.role}")
        st.divider()

        if st.button("Chat", use_container_width=True):
            nav("chat")

        if st.session_state.role == "patient":
            if st.button("My Appointments", use_container_width=True):
                nav("appointments")
            if st.button("My Profile", use_container_width=True):
                nav("profile")
            if st.button("Doctors", use_container_width=True):
                nav("doctors")

        if st.session_state.role == "doctor":
            if st.button("My Sessions", use_container_width=True):
                nav("sessions")
            if st.button("Queue", use_container_width=True):
                nav("queue")

        if st.session_state.role in ["nurse", "staff", "admin"]:
            if st.button("Queue", use_container_width=True):
                nav("queue")

        if st.session_state.role == "admin":
            if st.button("Admin Panel", use_container_width=True):
                nav("admin")

        st.divider()
        if st.button("New Chat", use_container_width=True):
            st.session_state.conversation_id = None
            st.session_state.chat_history = []
            nav("chat")
        if st.button("Logout", use_container_width=True):
            logout()
            st.rerun()

    # Page routing
    page = st.session_state.page

    if page == "chat":
        chat.render(send_message)
    elif page == "appointments":
        appointments.render(API_URL, api_headers())
    elif page == "profile":
        profile.render(API_URL, api_headers())
    elif page == "doctors":
        doctors.render(API_URL, api_headers())
    elif page == "sessions":
        sessions.render(API_URL, api_headers())
    elif page == "queue":
        queue.render(API_URL, api_headers(), role=st.session_state.role)
    elif page == "admin":
        admin_dashboard.render(API_URL, api_headers())
