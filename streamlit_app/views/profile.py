import streamlit as st
import requests


def render(api_url, headers):
    st.title("My Profile")

    res = requests.get(f"{api_url}/api/patient/profile", headers=headers)
    if res.status_code == 200:
        p = res.json()

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**UHID:** {p['uhid']}")
            st.write(f"**Name:** {p['name']}")
            st.write(f"**Email:** {p['email']}")
            st.write(f"**Phone:** {p['phone']}")
            st.write(f"**Gender:** {p['gender']}")
        with col2:
            st.write(f"**Blood Group:** {p['blood_group']}")
            st.write(f"**DOB:** {p['date_of_birth']}")
            st.write(f"**Address:** {p['address']}")
            st.write(f"**Emergency Contact:** {p['emergency_contact_name']} ({p['emergency_contact_phone']})")
            st.write(f"**Risk Score:** {p['risk_score']}")

        st.divider()
        st.subheader("Update My Details")

        with st.form("profile_form"):
            gender_opts = ["", "Male", "Female", "Other"]
            gender_idx = gender_opts.index(p["gender"]) if p["gender"] in gender_opts else 0
            blood_opts = ["", "A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]
            blood_idx = blood_opts.index(p["blood_group"]) if p["blood_group"] in blood_opts else 0

            new_name = st.text_input("Full Name", value=p["name"])
            new_phone = st.text_input("Phone", value=p["phone"])
            new_gender = st.selectbox("Gender", gender_opts, index=gender_idx)
            new_blood = st.selectbox("Blood Group", blood_opts, index=blood_idx)
            new_dob = st.text_input("Date of Birth (YYYY-MM-DD)", value=p["date_of_birth"])
            new_address = st.text_input("Address", value=p["address"])
            new_em_name = st.text_input("Emergency Contact Name", value=p["emergency_contact_name"])
            new_em_phone = st.text_input("Emergency Contact Phone", value=p["emergency_contact_phone"])
            submitted = st.form_submit_button("Update")

            if submitted:
                update_res = requests.put(f"{api_url}/api/patient/profile",
                    json={"full_name": new_name, "phone": new_phone, "gender": new_gender,
                          "blood_group": new_blood, "date_of_birth": new_dob, "address": new_address,
                          "emergency_contact_name": new_em_name, "emergency_contact_phone": new_em_phone},
                    headers=headers)
                if update_res.status_code == 200:
                    st.success("Profile updated!")
                else:
                    st.error("Update failed")
                st.rerun()
    else:
        st.error("Could not load profile")

    # Family Members
    st.divider()
    st.subheader("Family Members")

    ben_res = requests.get(f"{api_url}/api/patient/beneficiaries", headers=headers)
    if ben_res.status_code == 200:
        ben_data = ben_res.json()
        if ben_data["beneficiaries"]:
            for ben in ben_data["beneficiaries"]:
                with st.expander(f"{ben['name']} ({ben['uhid']}) — {ben['relationship']}"):
                    with st.form(f"edit_ben_{ben['uhid']}"):
                        gender_opts = ["", "Male", "Female", "Other"]
                        gender_idx = gender_opts.index(ben["gender"]) if ben["gender"] in gender_opts else 0
                        blood_opts = ["", "A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]
                        blood_idx = blood_opts.index(ben["blood_group"]) if ben["blood_group"] in blood_opts else 0

                        e_name = st.text_input("Full Name", value=ben["name"], key=f"n_{ben['uhid']}")
                        e_phone = st.text_input("Phone", value=ben["phone"], key=f"p_{ben['uhid']}")
                        e_gender = st.selectbox("Gender", gender_opts, index=gender_idx, key=f"g_{ben['uhid']}")
                        e_blood = st.selectbox("Blood Group", blood_opts, index=blood_idx, key=f"b_{ben['uhid']}")
                        e_dob = st.text_input("DOB (YYYY-MM-DD)", value=ben.get("date_of_birth", ""), key=f"d_{ben['uhid']}")
                        e_addr = st.text_input("Address", value=ben["address"], key=f"a_{ben['uhid']}")
                        e_em_name = st.text_input("Emergency Contact", value=ben["emergency_contact_name"], key=f"en_{ben['uhid']}")
                        e_em_phone = st.text_input("Emergency Phone", value=ben["emergency_contact_phone"], key=f"ep_{ben['uhid']}")
                        if st.form_submit_button("Save"):
                            requests.put(f"{api_url}/api/patient/beneficiaries",
                                json={"uhid": ben["uhid"], "full_name": e_name, "phone": e_phone,
                                      "gender": e_gender, "blood_group": e_blood, "date_of_birth": e_dob,
                                      "address": e_addr, "emergency_contact_name": e_em_name,
                                      "emergency_contact_phone": e_em_phone},
                                headers=headers)
                            st.success(f"{ben['name']} updated!")
                            st.rerun()
        else:
            st.info("No family members added yet.")

    st.subheader("Add Family Member")
    with st.form("add_ben_form"):
        ben_name = st.text_input("Full Name")
        ben_email = st.text_input("Email")
        ben_phone = st.text_input("Phone", key="new_ben_phone")
        ben_gender = st.selectbox("Gender", ["Male", "Female", "Other"], key="new_ben_gender")
        ben_blood = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"], key="new_ben_blood")
        ben_rel = st.selectbox("Relationship", ["spouse", "child", "parent", "sibling", "guardian", "other"])
        if st.form_submit_button("Register & Link"):
            if ben_name and ben_email:
                add_res = requests.post(f"{api_url}/api/patient/beneficiaries",
                    json={"full_name": ben_name, "email": ben_email, "phone": ben_phone,
                          "gender": ben_gender, "blood_group": ben_blood, "relationship": ben_rel},
                    headers=headers)
                if add_res.status_code == 200:
                    st.success(add_res.json().get("message", "Added!"))
                else:
                    st.error(add_res.json().get("detail", "Failed"))
                st.rerun()
