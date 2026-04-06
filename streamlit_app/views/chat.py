import streamlit as st


def render(send_message):
    st.title("HMS Chatbot")

    # Chat history
    chat_container = st.container(height=500)
    with chat_container:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    # Input
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([5, 1])
        with col1:
            user_input = st.text_input("Message", label_visibility="collapsed", placeholder="Type your message...")
        with col2:
            submitted = st.form_submit_button("Send", use_container_width=True)

    if submitted and user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.spinner("Thinking..."):
            reply = send_message(user_input)

        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.rerun()
