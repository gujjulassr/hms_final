import streamlit as st
import requests
from datetime import date


def render(api_url, headers):
    st.title("Admin Dashboard")

    # Show messages
    if "admin_msg" in st.session_state:
        msg_type, msg_text = st.session_state.admin_msg
        if msg_type == "success":
            st.success(msg_text)
        else:
            st.error(msg_text)
        del st.session_state.admin_msg

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Users", "Sessions", "Appointments", "Audit Log"])

    # ==========================================
    # OVERVIEW TAB
    # ==========================================
    with tab1:
        res = requests.get(f"{api_url}/api/admin/stats", headers=headers)
        if res.status_code == 200:
            s = res.json()
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Patients", s["total_patients"])
            col2.metric("Doctors", s["total_doctors"])
            col3.metric("Nurses", s["total_nurses"])
            col4.metric("Total Users", s["total_users"])

            st.divider()
            col1, col2, col3 = st.columns(3)
            col1.metric("Today's Appointments", s["today_appointments"])
            col2.metric("Completed", s["today_completed"])
            col3.metric("No-Shows", s["today_no_show"])

            # Departments
            st.divider()
            st.subheader("Departments")
            dept_res = requests.get(f"{api_url}/api/admin/departments", headers=headers)
            if dept_res.status_code == 200:
                for dept in dept_res.json()["departments"]:
                    st.write(f"**{dept['name']}** — {dept['doctors']} doctor(s)")

    # ==========================================
    # USERS TAB
    # ==========================================
    with tab2:
        # Filter
        role_filter = st.selectbox("Filter by role", ["", "patient", "doctor", "nurse", "admin"], format_func=lambda x: "All" if x == "" else x.title())

        if st.button("Refresh Users"):
            st.rerun()

        res = requests.get(f"{api_url}/api/admin/users", params={"role": role_filter}, headers=headers)
        if res.status_code == 200:
            users = res.json()["users"]
            st.write(f"**Total: {len(users)}**")

            for u in users:
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    st.write(f"**{u['full_name']}**")
                    st.caption(f"{u['email']} | {u['phone']}")
                with col2:
                    st.write(u["role"].upper())
                with col3:
                    if u["is_active"]:
                        st.success("Active")
                    else:
                        st.error("Inactive")
                with col4:
                    label = "Deactivate" if u["is_active"] else "Activate"
                    if st.button(label, key=f"tog_{u['id']}"):
                        r = requests.post(f"{api_url}/api/admin/users/toggle",
                            json={"user_id": u["id"]}, headers=headers)
                        if r.status_code == 200:
                            st.session_state.admin_msg = ("success", r.json()["message"])
                        else:
                            st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                        st.rerun()

                with st.expander(f"Edit {u['full_name']}"):
                    with st.form(f"edit_user_{u['id']}"):
                        e_name = st.text_input("Name", value=u["full_name"], key=f"en_{u['id']}")
                        e_email = st.text_input("Email", value=u["email"], key=f"ee_{u['id']}")
                        e_phone = st.text_input("Phone", value=u["phone"], key=f"ep_{u['id']}")
                        e_spec = ""
                        e_qual = ""
                        e_fee = -1
                        if u["role"] == "doctor":
                            e_spec = st.text_input("Specialization", value=u.get("specialization", ""), key=f"es_{u['id']}")
                            e_qual = st.text_input("Qualification", value=u.get("qualification", ""), key=f"eq_{u['id']}")
                            e_fee = st.number_input("Fee", min_value=0, value=u.get("consultation_fee", 0), key=f"ef_{u['id']}")
                            st.write(f"Rating: {u.get('avg_rating', 0)}/5")
                        if u["role"] == "patient":
                            st.write(f"UHID: {u.get('uhid', '')}")
                            st.write(f"Gender: {u.get('gender', '')} | Blood Group: {u.get('blood_group', '')}")
                            st.write(f"DOB: {u.get('date_of_birth', '')} | Address: {u.get('address', '')}")
                            st.write(f"Risk Score: {u.get('risk_score', 0)}")
                        if st.form_submit_button("Save"):
                            r = requests.put(f"{api_url}/api/admin/users",
                                json={"user_id": u["id"], "full_name": e_name, "email": e_email,
                                      "phone": e_phone, "specialization": e_spec,
                                      "qualification": e_qual, "consultation_fee": e_fee},
                                headers=headers)
                            if r.status_code == 200:
                                st.success(r.json()["message"])
                            else:
                                st.error(r.json().get("detail", "Failed"))
                st.divider()

        # Add user form
        st.subheader("Add New User")
        with st.form("add_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Full Name")
                new_email = st.text_input("Email")
                new_phone = st.text_input("Phone")
                new_pass = st.text_input("Password", type="password")
            with col2:
                new_role = st.selectbox("Role", ["patient", "doctor", "nurse", "admin"])
                new_spec = st.text_input("Specialization (doctors only)")
                new_qual = st.text_input("Qualification (doctors only)")
                new_fee = st.number_input("Consultation Fee (doctors only)", min_value=0, value=500)

            if st.form_submit_button("Create User"):
                if new_name and new_email and new_pass:
                    r = requests.post(f"{api_url}/api/admin/users",
                        json={
                            "full_name": new_name, "email": new_email, "phone": new_phone,
                            "password": new_pass, "role": new_role, "specialization": new_spec,
                            "qualification": new_qual, "consultation_fee": new_fee
                        }, headers=headers)
                    if r.status_code == 200:
                        st.session_state.admin_msg = ("success", r.json()["message"])
                    else:
                        st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                    st.rerun()
                else:
                    st.error("Name, email, and password are required.")

    # ==========================================
    # SESSIONS TAB
    # ==========================================
    with tab3:
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            sess_date = st.date_input("Date", value=date.today(), key="admin_sess_date")
        with col_f2:
            # Get departments for filter
            dept_res = requests.get(f"{api_url}/api/admin/departments", headers=headers)
            dept_options = ["All"]
            if dept_res.status_code == 200:
                dept_options += [d["name"] for d in dept_res.json()["departments"]]
            dept_filter = st.selectbox("Department", dept_options)
        with col_f3:
            doc_filter = st.text_input("Doctor name", placeholder="Leave empty for all")

        if st.button("Refresh Sessions"):
            st.rerun()

        params = {"session_date": str(sess_date)}
        if dept_filter != "All":
            params["department"] = dept_filter
        if doc_filter:
            params["doctor_name"] = doc_filter

        res = requests.get(f"{api_url}/api/admin/sessions", params=params, headers=headers)
        if res.status_code == 200:
            sessions = res.json()["sessions"]
            if not sessions:
                st.info("No sessions found.")
            else:
                st.write(f"**Total: {len(sessions)} sessions**")
                for sess in sessions:
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.write(f"**{sess['doctor']}** ({sess['department']})")
                        st.write(f"{sess['date']} | {sess['start_time']} - {sess['end_time']}")
                        st.caption(f"Slots: {sess['total_slots']} | Overtime: {sess['overtime']}min | Delay: {sess['delay']}min")
                    with col2:
                        status = sess["status"]
                        if status == "scheduled":
                            st.warning("SCHEDULED")
                        elif status == "active":
                            st.success("ACTIVE")
                        elif status == "completed":
                            st.info("COMPLETED")
                    with col3:
                        is_afternoon = sess["start_time"] >= "12:00"
                        if sess["status"] == "scheduled":
                            col_a, col_b = st.columns(2)
                            with col_a:
                                if st.button("Activate", key=f"aact_{sess['id']}"):
                                    r = requests.post(f"{api_url}/api/doctor/activate-session",
                                        json={"session_id": sess["id"]}, headers=headers)
                                    if r.status_code == 200:
                                        st.session_state.admin_msg = ("success", r.json()["message"])
                                    else:
                                        st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                                    st.rerun()
                            with col_b:
                                if st.button("Cancel", key=f"acan_{sess['id']}"):
                                    r = requests.post(f"{api_url}/api/doctor/cancel-session",
                                        json={"session_id": sess["id"]}, headers=headers)
                                    if r.status_code == 200:
                                        st.session_state.admin_msg = ("success", r.json()["message"])
                                    else:
                                        st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                                    st.rerun()
                        elif sess["status"] == "active":
                            # col_a, col_b = st.columns(2)
                            # with col_a:
                            #     if st.button("Revert to Scheduled", key=f"arev_{sess['id']}"):
                            #         r = requests.post(f"{api_url}/api/admin/revert-session",
                            #             json={"session_id": sess["id"]}, headers=headers)
                            #         if r.status_code == 200:
                            #             st.session_state.admin_msg = ("success", r.json()["message"])
                            #         else:
                            #             st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                            #         st.rerun()
                            # with col_b:
                            #     if st.button("Cancel", key=f"acan2_{sess['id']}"):
                            #         r = requests.post(f"{api_url}/api/doctor/cancel-session",
                            #             json={"session_id": sess["id"]}, headers=headers)
                            #         if r.status_code == 200:
                            #             st.session_state.admin_msg = ("success", r.json()["message"])
                            #         else:
                            #             st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                            #     st.rerun()

                            if st.button("Cancel", key=f"acan2_{sess['id']}"):
                                r = requests.post(f"{api_url}/api/doctor/cancel-session",
                                    json={"session_id": sess["id"]}, headers=headers)                                                                                                             
                                if r.status_code == 200:                             
                                    st.session_state.admin_msg = ("success", r.json()["message"])                                                                                                 
                                else:                                                                                                                                                             
                                    st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                            if is_afternoon:
                                # Build time options from current end time to 23:45
                                from datetime import datetime as dt, timedelta as td
                                current_end = dt.strptime(sess["end_time"], "%H:%M:%S")

                                print(f"[DEBUG] end_time={sess['end_time']}, overtime={sess['overtime']}, current_end={current_end}") 
                                 

                                # if sess["overtime"] > 0:
                                #     current_end = current_end + td(minutes=sess["overtime"])
                                time_options = []


                                # print(f"[DEBUG] current_end after overtime={current_end}") 


                                # print(f"[DEBUG] is_afternoon={is_afternoon}, status={sess['status']}, time_options={len(time_options) if time_options else 0}") 
                                


                                original_end=dt.strptime(sess["original_end_time"],"%H:%M:%S")
                                now=dt.combine(original_end.date(), dt.now().time())
                                minutes = now.minute
                                rounded = minutes + (15 - minutes % 15) if minutes % 15 != 0 else minutes 
                                now=now.replace(minute=0,second=0)+td(minutes=rounded)
                                start_from = max(original_end, now)

                                # t = current_end + td(minutes=15)
                                t = start_from + td(minutes=15)

                                print(f"[DEBUG] start_form :{start_from}")

                                # print(f"[DEBUG] t={t}, t.hour={t.hour}")
                                while t.hour < 24 and t.day==start_from.day:
                                    time_options.append(t.strftime("%H:%M"))
                                    t = t + td(minutes=15)


                                # print(f"[Debug time options] {time_options}")
                                if time_options:
                                    new_end = st.selectbox("Extend to", time_options, key=f"aext_{sess['id']}")
                                    if st.button("Extend", key=f"aextbtn_{sess['id']}"):
                                        new_end_dt = dt.strptime(new_end, "%H:%M")
                                        ext_min = int((new_end_dt - original_end).total_seconds() / 60)
                                        r = requests.post(f"{api_url}/api/doctor/extend-session",
                                            json={"extra_minutes": ext_min, "session_id": sess["id"]}, headers=headers)
                                        if r.status_code == 200:
                                            st.success(r.json()["message"])
                                        else:
                                            st.error(r.json().get("detail", "Failed"))
                    st.divider()

        # Create session + Activate/Revert actions
        st.subheader("Create New Session")
        # Get all doctors for dropdown
        doc_res = requests.get(f"{api_url}/api/admin/users", params={"role": "doctor"}, headers=headers)
        doc_names = []
        if doc_res.status_code == 200:
            doc_names = [u["full_name"] for u in doc_res.json()["users"]]

        with st.form("admin_create_session"):
            col1, col2 = st.columns(2)
            with col1:
                from datetime import timedelta as tdelta
                sess_doc = st.selectbox("Doctor", doc_names) if doc_names else st.text_input("Doctor Name")
                sess_date = st.date_input("Date", value=date.today() + tdelta(days=1), min_value=date.today(), key="admin_create_date")
            with col2:
                sess_start = st.selectbox("Start Time", ["09:00", "10:00", "11:00", "14:00", "15:00"], key="admin_create_start")
                sess_end = st.selectbox("End Time", ["13:00", "14:00", "17:00", "18:00"], key="admin_create_end")

            if st.form_submit_button("Create Session"):
                r = requests.post(f"{api_url}/api/chat/message",
                    json={"message": f"create session for {sess_doc} on {sess_date} from {sess_start} to {sess_end}"},
                    headers=headers)
                if r.status_code == 200:
                    st.success(r.json().get("reply", "Session created"))
                else:
                    st.session_state.admin_msg = ("error", "Failed to create session")
                    # st.rerun()

    # ==========================================
    # APPOINTMENTS TAB
    # ==========================================
    with tab4:
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            appt_date = st.date_input("Date", value=date.today(), key="admin_appt_date")
        with col_f2:
            dept_res2 = requests.get(f"{api_url}/api/admin/departments", headers=headers)
            dept_opts2 = ["All"]
            if dept_res2.status_code == 200:
                dept_opts2 += [d["name"] for d in dept_res2.json()["departments"]]
            appt_dept = st.selectbox("Department", dept_opts2, key="appt_dept")
        with col_f3:
            appt_doc = st.text_input("Doctor", placeholder="All", key="appt_doc")
        with col_f4:
            appt_status = st.selectbox("Status", ["All", "booked", "checked_in", "in_progress", "completed", "cancelled", "no_show"], key="appt_status")

        if st.button("Refresh Appointments"):
            st.rerun()

        params = {"session_date": str(appt_date)}
        if appt_dept != "All":
            params["department"] = appt_dept
        if appt_doc:
            params["doctor_name"] = appt_doc
        if appt_status != "All":
            params["status"] = appt_status

        res = requests.get(f"{api_url}/api/admin/appointments", params=params, headers=headers)
        if res.status_code == 200:
            appts = res.json()["appointments"]
            if not appts:
                st.info("No appointments found.")
            else:
                st.write(f"**Total: {len(appts)} appointments**")
                for appt in appts:
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        label = f"**{appt['patient_name']}** ({appt['uhid']})"
                        if appt["is_emergency"]:
                            label += " [EMERGENCY]"
                        st.write(label)
                        st.caption(f"{appt['doctor']} ({appt['department']}) | {appt['date']} at {appt['time']} | Slot {appt['slot']}")
                    with col2:
                        st.write(f"Priority: {appt['priority']}")
                    with col3:
                        s = appt["status"]
                        if s == "booked":
                            st.warning("BOOKED")
                        elif s == "checked_in":
                            st.info("CHECKED IN")
                        elif s == "in_progress":
                            st.success("IN PROGRESS")
                        elif s == "completed":
                            st.success("COMPLETED")
                        elif s in ["cancelled", "no_show"]:
                            st.error(s.upper())
                    with col4:
                        s = appt["status"]
                        if s == "booked":
                            col_a, col_b = st.columns(2)
                            with col_a:
                                if st.button("Check In", key=f"aci_{appt['uhid']}_{appt['slot']}"):
                                    r = requests.post(f"{api_url}/api/doctor/checkin-patient",
                                        json={"patient_uhid": appt["uhid"]}, headers=headers)
                                    if r.status_code == 200:
                                        st.session_state.admin_msg = ("success", r.json()["message"])
                                    else:
                                        st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                                    st.rerun()
                            with col_b:
                                if st.button("Cancel", key=f"acanc_{appt['uhid']}_{appt['slot']}"):
                                    r = requests.post(f"{api_url}/api/chat/message",
                                        json={"message": f"cancel appointment for {appt['uhid']} with {appt['doctor']}"}, headers=headers)
                                    st.session_state.admin_msg = ("success", "Appointment cancelled.")
                                    st.rerun()
                        elif s == "checked_in":
                            col_a, col_b = st.columns(2)
                            with col_a:
                                if st.button("Call", key=f"acall_{appt['uhid']}_{appt['slot']}"):
                                    r = requests.post(f"{api_url}/api/doctor/call-patient",
                                        json={"patient_uhid": appt["uhid"]}, headers=headers)
                                    if r.status_code == 200:
                                        st.session_state.admin_msg = ("success", r.json()["message"])
                                    else:
                                        st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                                    st.rerun()
                            with col_b:
                                if st.button("Cancel", key=f"acanc2_{appt['uhid']}_{appt['slot']}"):
                                    r = requests.post(f"{api_url}/api/chat/message",
                                        json={"message": f"cancel appointment for {appt['uhid']} with {appt['doctor']}"}, headers=headers)
                                    st.session_state.admin_msg = ("success", "Appointment cancelled.")
                                    st.rerun()
                        elif s == "in_progress":
                            if st.button("Complete", key=f"acomp_{appt['uhid']}_{appt['slot']}"):
                                r = requests.post(f"{api_url}/api/doctor/complete-patient",
                                    json={"patient_uhid": appt["uhid"]}, headers=headers)
                                if r.status_code == 200:
                                    st.session_state.admin_msg = ("success", r.json()["message"])
                                else:
                                    st.session_state.admin_msg = ("error", r.json().get("detail", "Failed"))
                                st.rerun()
                    st.divider()

    # ==========================================
    # AUDIT LOG TAB
    # ==========================================
    with tab5:
        if st.button("Refresh Log"):
            st.rerun()

        res = requests.get(f"{api_url}/api/admin/audit", params={"limit": 50}, headers=headers)
        if res.status_code == 200:
            logs = res.json()["logs"]
            if not logs:
                st.info("No audit entries.")
            else:
                for log in logs:
                    col1, col2, col3 = st.columns([1, 2, 2])
                    with col1:
                        st.caption(log["timestamp"])
                    with col2:
                        st.write(f"**{log['user']}** — {log['action']}")
                    with col3:
                        st.caption(f"{log['target_type']} | {log['details']}")
