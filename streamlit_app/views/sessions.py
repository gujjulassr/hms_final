import streamlit as st
import requests
from datetime import date, timedelta, datetime


def render(api_url, headers):
    st.title("My Sessions")

    # Show any stored messages
    if "session_msg" in st.session_state:
        msg_type, msg_text = st.session_state.session_msg
        if msg_type == "success":
            st.success(msg_text)
        elif msg_type == "error":
            st.error(msg_text)
        del st.session_state.session_msg

    filter_date = st.date_input("Select date", value=date.today())

    if st.button("Refresh"):
        st.rerun()

    st.divider()

    res = requests.get(f"{api_url}/api/doctor/my-sessions", headers=headers)
    if res.status_code != 200:
        st.error("Could not load sessions")
        return

    data = res.json()
    sessions = [s for s in data["sessions"] if s.get("date") == str(filter_date)]

    is_today = filter_date == date.today()
    is_future = filter_date > date.today()
    is_past = filter_date < date.today()

    if not sessions:
        st.info(f"No sessions on {filter_date}.")
    else:
        for sess in sessions:
            status = sess["status"]
            is_afternoon = sess["start_time"] >= "12:00"

            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{sess['start_time']} - {sess['end_time']}**")
                info = f"Slots: {sess['total_slots']} | Booked: {sess['booked']}"
                if sess["overtime_minutes"] > 0:
                    info += f" | Overtime: {sess['overtime_minutes']}min"
                if sess["delay_minutes"] > 0:
                    info += f" | Delay: {sess['delay_minutes']}min"
                st.write(info)
            with col2:
                if status == "scheduled":
                    st.warning("SCHEDULED")
                elif status == "active":
                    st.success("ACTIVE")
                elif status == "completed":
                    st.info("COMPLETED")
                elif status == "cancelled":
                    st.error("CANCELLED")

            # Actions
            if status == "scheduled":
                if is_past:
                    st.caption("Past session — no actions available.")
                elif is_future:
                    if st.button("Cancel Session", key=f"can_{sess['id']}", use_container_width=True):
                        st.session_state[f"confirm_cancel_{sess['id']}"] = True

                    if st.session_state.get(f"confirm_cancel_{sess['id']}"):
                        st.warning("Cancel this session? All appointments will be cancelled.")
                        col_y, col_n = st.columns(2)
                        with col_y:
                            if st.button("Yes, Cancel", key=f"yes_{sess['id']}"):
                                r = requests.post(f"{api_url}/api/chat/message",
                                    json={"message": "cancel my session"}, headers=headers)
                                st.session_state[f"confirm_cancel_{sess['id']}"] = False
                                st.session_state.session_msg = ("success", "Session cancelled.")
                                st.rerun()
                        with col_n:
                            if st.button("No", key=f"no_{sess['id']}"):
                                st.session_state[f"confirm_cancel_{sess['id']}"] = False
                                st.rerun()
                    st.caption("Activate is only available on the day of the session.")
                else:
                    # Today — can activate
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("Activate", key=f"act_{sess['id']}", use_container_width=True):
                            r = requests.post(f"{api_url}/api/doctor/activate-session", headers=headers)
                            if r.status_code == 200:
                                st.session_state.session_msg = ("success", r.json()["message"])
                            else:
                                st.session_state.session_msg = ("error", r.json().get("detail", "Failed"))
                            st.rerun()
                    with col_b:
                        if st.button("Cancel Session", key=f"cant_{sess['id']}", use_container_width=True):
                            st.session_state[f"confirm_cancel_{sess['id']}"] = True

                        if st.session_state.get(f"confirm_cancel_{sess['id']}"):
                            st.warning("Cancel this session? All appointments will be cancelled.")
                            col_y, col_n = st.columns(2)
                            with col_y:
                                if st.button("Yes", key=f"yesc_{sess['id']}"):
                                    r = requests.post(f"{api_url}/api/doctor/cancel-session",
                                        json={"session_id": sess["id"]}, headers=headers)
                                    st.session_state[f"confirm_cancel_{sess['id']}"] = False
                                    if r.status_code == 200:
                                        st.session_state.session_msg = ("success", r.json()["message"])
                                    else:
                                        st.session_state.session_msg = ("error", r.json().get("detail", "Failed"))
                                    st.rerun()
                            with col_n:
                                if st.button("No", key=f"noc_{sess['id']}"):
                                    st.session_state[f"confirm_cancel_{sess['id']}"] = False
                                    st.rerun()

            elif status == "active":
                if st.button("Complete Session", key=f"comp_{sess['id']}", use_container_width=True):
                    st.session_state[f"confirm_complete_{sess['id']}"] = True

                if st.session_state.get(f"confirm_complete_{sess['id']}"):
                    st.warning("Complete? Unchecked → no-show. Checked-in → propagated or cancelled.")
                    col_y, col_n = st.columns(2)
                    with col_y:
                        if st.button("Yes, Complete", key=f"ycomp_{sess['id']}"):
                            r = requests.post(f"{api_url}/api/doctor/complete-session", headers=headers)
                            if r.status_code == 200:
                                st.session_state.session_msg = ("success", r.json()["message"])
                            else:
                                st.session_state.session_msg = ("error", r.json().get("detail", "Failed"))
                            st.session_state[f"confirm_complete_{sess['id']}"] = False
                            st.rerun()
                    with col_n:
                        if st.button("No", key=f"ncomp_{sess['id']}"):
                            st.session_state[f"confirm_complete_{sess['id']}"] = False
                            st.rerun()

                # Extend — only afternoon active
                if is_afternoon:
                    from datetime import datetime as dt, timedelta as td
                    current_end = dt.strptime(sess["end_time"], "%H:%M:%S")
                    if sess["overtime_minutes"] > 0:
                        current_end = current_end + td(minutes=sess["overtime_minutes"])
                    time_options = []
                    t = current_end + td(minutes=15)
                    while t.hour < 24:
                        time_options.append(t.strftime("%H:%M"))
                        t = t + td(minutes=15)
                    if time_options:
                        col_e1, col_e2 = st.columns([3, 1])
                        with col_e1:
                            new_end = st.selectbox("Extend to", time_options, key=f"ext_{sess['id']}")
                        with col_e2:
                            if st.button("Extend", key=f"extbtn_{sess['id']}", use_container_width=True):
                                new_end_dt = dt.strptime(new_end, "%H:%M")
                                ext_min = int((new_end_dt - current_end).total_seconds() / 60)
                                r = requests.post(f"{api_url}/api/doctor/extend-session",
                                    json={"extra_minutes": ext_min}, headers=headers)
                            if r.status_code == 200:
                                st.session_state.session_msg = ("success", r.json()["message"])
                            else:
                                st.session_state.session_msg = ("error", r.json().get("detail", "Failed"))
                            st.rerun()
                else:
                    st.caption("Morning sessions cannot be extended.")

            st.divider()

    # Create new session
    st.subheader("Create New Session")
    with st.form("create_session_form"):
        col1, col2 = st.columns(2)
        with col1:
            sess_date = st.date_input("Date", value=date.today() + timedelta(days=1), min_value=date.today())
            sess_start = st.selectbox("Start Time", ["09:00", "10:00", "11:00", "14:00", "15:00"])
        with col2:
            sess_end = st.selectbox("End Time", ["13:00", "14:00", "17:00", "18:00"])
            slot_dur = st.selectbox("Slot Duration (min)", [10, 15, 20, 30], index=1)

        if st.form_submit_button("Create Session"):
            start_h = int(sess_start.split(":")[0])
            end_h = int(sess_end.split(":")[0])
            if start_h >= end_h:
                st.error("Start time must be before end time.")
            elif sess_date == date.today() and datetime.strptime(sess_end, "%H:%M").time() < datetime.now().time():
                st.error("Cannot create a session that has already passed today.")
            else:
                r = requests.post(f"{api_url}/api/doctor/create-session",
                    json={"session_date": str(sess_date), "start_time": sess_start, "end_time": sess_end, "slot_duration": slot_dur},
                    headers=headers)
                if r.status_code == 200:
                    st.session_state.session_msg = ("success", r.json()["message"])
                else:
                    st.session_state.session_msg = ("error", r.json().get("detail", "Failed"))
                st.rerun()
