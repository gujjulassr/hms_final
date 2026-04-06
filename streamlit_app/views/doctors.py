import streamlit as st
import requests


def render(api_url, headers):
    st.title("Available Doctors")

    if st.button("Refresh"):
        st.rerun()

    res = requests.get(f"{api_url}/api/patient/doctors", headers=headers)
    if res.status_code == 200:
        data = res.json()
        for doc in data["doctors"]:
            with st.expander(f"{doc['name']} - {doc['specialization']}", expanded=True):
                col1, col2, col3 = st.columns(3)
                col1.metric("Fee", f"{doc['fee']}")
                col2.metric("Rating", f"{doc['rating']:.1f}/5")
                col3.metric("Reviews", doc['total_ratings'])

                if doc["sessions_today"]:
                    st.write("**Today's Sessions:**")
                    for sess in doc["sessions_today"]:
                        st.write(f"  {sess['start_time']} - {sess['end_time']} | Status: {sess['status']} | Available: {sess['available']}/{sess['capacity']}")
                else:
                    st.write("No sessions today")
