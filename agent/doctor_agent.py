from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from config.settings import OPENAI_API_KEY
from tools.queue_tools import get_queue, call_next, call_patient, complete_appointment, get_my_patients, get_my_sessions, set_priority
from tools.session_tools import create_session, activate_session, complete_session, extend_session, cancel_session
from tools.report_tools import generate_session_report


class DoctorState(TypedDict):
    messages: Annotated[list, add_messages]
    user_info: str


doctor_tools = [get_queue, call_next, call_patient, complete_appointment, get_my_patients, get_my_sessions, set_priority, create_session, activate_session, complete_session, extend_session, cancel_session, generate_session_report]

llm = ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY)
llm_with_tools = llm.bind_tools(doctor_tools)


async def doctor_chatbot(state: DoctorState):
    user_info = state.get("user_info", "")
    system_msg = SystemMessage(content=f"""You are a Hospital Management System assistant for DOCTORS.
        Keep answers SHORT and RELEVANT. Only show what was asked. Do not dump extra data.
        You MUST use tools to fetch data. Never make up information.

        Current logged-in doctor: {user_info}
        Use their name from above. NEVER ask for name.

        Tool selection rules:
        - 'my sessions' / 'active session' / 'session details' → use get_my_sessions. Brief answer.
        - 'my patients' / 'who visited' / 'patient list' → use get_my_patients.
        - 'queue' / 'waiting' / 'who is next' → use get_queue.
        - 'extend' past/completed session → say "Cannot extend completed/past sessions."
        - 'activate' when all completed → say "All sessions completed for today."
        - Use ONLY ONE tool per question. Do not combine tools unless asked.""")
    messages = [system_msg] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    print(f"\n[DEBUG] Tool calls: {response.tool_calls}")
    print(f"[DEBUG] Response: {response.content[:100] if response.content else 'no content'}\n")
    return {"messages": [response]}


def doctor_should_continue(state: DoctorState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


doctor_graph = StateGraph(DoctorState)
doctor_graph.add_node("doctor_chatbot", doctor_chatbot)
doctor_graph.add_node("tools", ToolNode(doctor_tools))
doctor_graph.add_edge("tools", "doctor_chatbot")
doctor_graph.add_conditional_edges("doctor_chatbot", doctor_should_continue, {"tools": "tools", END: END})
doctor_graph.set_entry_point("doctor_chatbot")

doctor_app = doctor_graph.compile()
