import streamlit as st
import requests


def render(api_url, headers):
    st.title("My Appointments")

    if st.button("Refresh"):
        st.rerun()

    # Live status
    status_res = requests.get(f"{api_url}/api/patient/status", headers=headers)
    if status_res.status_code == 200:
        status_data = status_res.json()
        st.write(f"**UHID:** {status_data['uhid']} | **Name:** {status_data['name']}")

        if status_data["has_appointment_today"]:
            st.subheader("Today - Live Status")
            for appt in status_data["appointments"]:
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**{appt['doctor']}** ({appt['specialization']}) | Time: {appt['time']} | Slot {appt['slot_number']}")
                with col2:
                    if appt["status"] == "booked":
                        st.warning("Not checked in")
                    elif appt["status"] == "checked_in":
                        st.success("Checked in")
                    elif appt["status"] == "in_progress":
                        st.success("Your turn!")
                st.info(appt["message"])
                if appt["patients_ahead"] > 0:
                    st.write(f"Patients ahead: **{appt['patients_ahead']}**")
                if appt.get("estimated_wait_minutes", 0) > 0:
                    st.write(f"Estimated wait: **~{appt['estimated_wait_minutes']} minutes**")
                st.divider()

    # History
    st.subheader("Appointment History")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        date_filter = st.date_input("Filter by date", value=None)
    with col_f2:
        status_filter = st.selectbox("Filter by status", ["All", "booked", "checked_in", "in_progress", "completed", "cancelled", "no_show"])

    appt_res = requests.get(f"{api_url}/api/patient/appointments", headers=headers)
    if appt_res.status_code == 200:
        appt_data = appt_res.json()
        appointments = appt_data["appointments"]

        if date_filter:
            appointments = [a for a in appointments if a["date"] == str(date_filter)]
        if status_filter != "All":
            appointments = [a for a in appointments if a["status"] == status_filter]

        if not appointments:
            st.info("No appointments found.")
        else:
            st.write(f"**Total: {len(appointments)}**")
            for appt in appointments:
                col1, col2 = st.columns([3, 1])
                with col1:
                    label = f"{appt['doctor']} ({appt['specialization']})"
                    if appt["is_emergency"]:
                        label += " [EMERGENCY]"
                    st.write(f"**{label}**")
                    st.write(f"{appt['date']} at {appt['time']} | Slot {appt['slot']}")
                    if appt["notes"]:
                        st.write(f"Notes: {appt['notes']}")
                with col2:
                    status = appt["status"]
                    if status == "completed":
                        st.success(status.upper())
                    elif status in ["cancelled", "no_show"]:
                        st.error(status.upper())
                    elif status == "booked":
                        st.warning("BOOKED")
                    elif status == "checked_in":
                        st.info("CHECKED IN")
                    elif status == "in_progress":
                        st.success("IN PROGRESS")
                st.divider()
