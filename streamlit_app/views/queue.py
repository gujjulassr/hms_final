import streamlit as st
import requests


def render(api_url, headers, role="doctor"):
    st.title("Patient Queue")

    # Doctor selector for admin/nurse
    if "selected_doctor" not in st.session_state:
        st.session_state.selected_doctor = ""

    if role in ["nurse", "staff", "admin"]:
        doc_res = requests.get(f"{api_url}/api/patient/doctors", headers=headers)
        doc_names = [""]
        if doc_res.status_code == 200:
            doc_names += [d["name"] for d in doc_res.json()["doctors"]]
        selected = st.selectbox("Select Doctor", doc_names, format_func=lambda x: "Choose a doctor" if x == "" else x)
        st.session_state.selected_doctor = selected

    col_r, col_auto = st.columns([1, 1])
    with col_r:
        if st.button("Refresh", use_container_width=True):
            st.rerun()
    with col_auto:
        auto = st.checkbox("Auto-refresh (10s)")

    # Emergency booking for nurse/admin
    if role in ["nurse", "staff", "admin"] and st.session_state.selected_doctor:
        with st.expander("Emergency Booking"):
            emerg_uhid = st.text_input("Patient UHID", placeholder="HMS-2026-XXXXX", key="emerg_uhid")
            if st.button("Emergency Book", use_container_width=True):
                if emerg_uhid:
                    res = requests.post(f"{api_url}/api/doctor/emergency-book",
                        json={"patient_uhid": emerg_uhid, "doctor_name": st.session_state.selected_doctor}, headers=headers)
                    if res.status_code == 200:
                        st.success(res.json()["message"])
                    else:
                        st.error(res.json().get("detail", "Failed"))
                    st.rerun()

    st.divider()

    # Queue display
    params = {}
    if role in ["nurse", "staff", "admin"] and st.session_state.selected_doctor:
        params["doctor_name"] = st.session_state.selected_doctor
    res = requests.get(f"{api_url}/api/doctor/queue", params=params, headers=headers)
    if res.status_code == 200:
        data = res.json()
        st.write(f"**Doctor:** {data.get('doctor', '')}")

        if not data.get("session_active") and not data.get("session_status"):
            st.warning("No session found for this doctor today.")
        else:
            sess_status = data.get("session_status", "")
            if sess_status == "active":
                st.success(f"**Session:** {data.get('session_time', '')} — ACTIVE")
            else:
                st.warning(f"**Session:** {data.get('session_time', '')} — SCHEDULED (not yet activated)")
            st.divider()

            # Emergency queue
            if data["emergency_queue"]:
                st.subheader("Emergency Queue")
                for p in data["emergency_queue"]:
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        st.write(f"**{p['name']}** ({p['uhid']}) — {p['age_group']}")
                    with col2:
                        st.error(f"{p['priority']}")
                    with col3:
                        if p["status"] == "checked_in":
                            if st.button("Call", key=f"call_e_{p['uhid']}"):
                                requests.post(f"{api_url}/api/doctor/call-patient",
                                    json={"patient_uhid": p["uhid"]}, headers=headers)
                                st.rerun()
                        elif p["status"] == "in_progress":
                            st.success("With Doctor")
                    with col4:
                        if p["status"] == "in_progress":
                            with st.popover("Complete"):
                                notes = st.text_input("Notes", key=f"notes_e_{p['uhid']}")
                                if st.button("Confirm", key=f"comp_e_{p['uhid']}"):
                                    requests.post(f"{api_url}/api/doctor/complete-patient",
                                        json={"patient_uhid": p["uhid"], "notes": notes}, headers=headers)
                                    st.rerun()
                st.divider()

            # Normal queue
            st.subheader("Normal Queue")
            if data["normal_queue"]:
                current_slot = None
                for p in data["normal_queue"]:
                    if p["slot"] != current_slot:
                        current_slot = p["slot"]
                        st.write(f"**Slot {current_slot} ({p['time']})**")

                    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                    with col1:
                        st.write(f"{p['name']} ({p['uhid']}) — {p['age_group']}")
                    with col2:
                        priority_opts = ["NORMAL", "HIGH", "CRITICAL"]
                        current_idx = priority_opts.index(p["priority"]) if p["priority"] in priority_opts else 0
                        new_priority = st.selectbox("Priority", priority_opts, index=current_idx, key=f"pri_{p['uhid']}", label_visibility="collapsed")
                        # if new_priority != p["priority"]:
                        #     requests.post(f"{api_url}/api/doctor/set-priority",
                        #         json={"patient_uhid": p["uhid"], "priority": new_priority}, headers=headers)
                        #     st.rerun()

                        if new_priority != p["priority"]:
                              r = requests.post(f"{api_url}/api/doctor/set-priority",
                                  json={"patient_uhid": p["uhid"], "priority": new_priority}, headers=headers)
                              if r.status_code == 200:                                                                                                                      
                                  st.success(f"Priority set to {new_priority}")
                              else:                                                                                                                                         
                                  st.error(r.json().get("detail", "Failed")) 
                    with col3:
                        if p["status"] == "checked_in":
                            st.warning("Waiting")
                        elif p["status"] == "in_progress":
                            st.success("With Doctor")
                    with col4:
                        if p["status"] == "checked_in":
                            if st.button("Call", key=f"call_{p['uhid']}"):
                                requests.post(f"{api_url}/api/doctor/call-patient",
                                    json={"patient_uhid": p["uhid"]}, headers=headers)
                                st.rerun()
                    with col5:
                        if p["status"] == "in_progress":
                            with st.popover("Complete"):
                                notes = st.text_input("Notes", key=f"notes_{p['uhid']}")
                                if st.button("Confirm", key=f"comp_{p['uhid']}"):
                                    requests.post(f"{api_url}/api/doctor/complete-patient",
                                        json={"patient_uhid": p["uhid"], "notes": notes}, headers=headers)
                                    st.rerun()
            else:
                st.info("No patients in queue.")

            # Booked patients (not yet checked in)
            if data.get("booked_queue"):
                st.divider()
                st.subheader("Booked — Awaiting Check-in")
                for p in data["booked_queue"]:
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        st.write(f"{p['name']} ({p['uhid']}) — {p['age_group']}")
                        st.caption(f"Slot {p['slot']} at {p['time']}")
                    with col2:
                        st.warning("BOOKED")
                    with col3:
                        if st.button("Check In", key=f"bci_{p['uhid']}"):
                            requests.post(f"{api_url}/api/doctor/checkin-patient",
                                json={"patient_uhid": p["uhid"]}, headers=headers)
                            st.rerun()
                    with col4:
                        if st.button("Cancel", key=f"bcan_{p['uhid']}"):
                            # requests.post(f"{api_url}/api/chat/message",
                            #     json={"message": f"cancel appointment for {p['uhid']} with {data.get('doctor', '')}"}, headers=headers)

                            requests.post(f"{api_url}/api/doctor/cancel-appointment",
                                json={"patient_uhid": p["uhid"]}, headers=headers)   
                            st.rerun()

    # Auto-refresh
    if auto:
        import time
        time.sleep(10)
        st.rerun()
