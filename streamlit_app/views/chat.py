import requests
import streamlit as st


def render(send_message,API_URL, api_headers):
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


    st.divider()                                                                                                                                                              
    st.write("**Recent Chats**")                                                                                                                                            
    conv_res = requests.get(f"{API_URL}/api/chat/conversations", headers=api_headers)
    if conv_res.status_code == 200:                                                                                                                                           
        for conv in conv_res.json()["conversations"]:                                                                                                                         
            if st.button(conv["preview"][:30] + "...", key=f"conv_{conv['id']}"):                                                                                             
                st.session_state.conversation_id = conv["id"]                                                                                                                 
                # Load messages                                                                                                                                               
                hist_res = requests.get(f"{API_URL}/api/chat/history/{conv['id']}", headers=api_headers)                                                                    
                if hist_res.status_code == 200:                                                                                                                               
                    from langchain_core.messages import HumanMessage, AIMessage                                                                                             
                    st.session_state.chat_history = []                                                                                                                        
                    for msg in hist_res.json()["messages"]:                                                                                                                   
                        role = "user" if msg["sender"] == "user" else "assistant"
                        st.session_state.chat_history.append({"role": role, "content": msg["content"]})                                                                       
                st.session_state.page = "chat"                                                                                                                              
                st.rerun()    
