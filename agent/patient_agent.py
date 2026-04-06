from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from config.settings import OPENAI_API_KEY
from tools.patient_tools import update_patient, register_patient, add_beneficiary, get_my_beneficiaries
from tools.doctor_tools import search_doctors
from tools.session_tools import check_availability
from tools.appointment_tools import book_appointment, get_my_appointments, cancel_appointment,check_earliest_slot
from tools.rating_tools import submit_rating, get_doctor_ratings, search_feedback
from tools.report_tools import generate_patient_report


class PatientState(TypedDict):
    messages: Annotated[list, add_messages]
    user_info: str


patient_tools = [register_patient, update_patient, add_beneficiary, get_my_beneficiaries, search_doctors, check_availability, book_appointment, get_my_appointments, cancel_appointment, submit_rating, get_doctor_ratings, search_feedback, generate_patient_report,check_earliest_slot]

llm = ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY)
llm_with_tools = llm.bind_tools(patient_tools)


async def patient_chatbot(state: PatientState):
    user_info = state.get("user_info", "")
    system_msg = SystemMessage(content=f"""You are a Hospital Management System assistant for PATIENTS.
        You can help patients search doctors, check availability, book/cancel appointments, and view their details.
        You MUST use tools to fetch data. Never make up information.
        When searching by specialization, use base medical terms (e.g., 'cardiology' not 'cardiologist').
        To list all doctors, use search_doctors with an empty string.
        When user asks for doctors other than a specific one, first list all doctors then filter.
        When passing doctor names to tools, use only the last name without 'Dr.' prefix (e.g., 'Shah' not 'Dr. Shah').
        NEVER book an appointment without explicit confirmation from the patient. If they ask 'what is the earliest slot', only check availability and tell them. Only book when they say 'book', 'confirm', or 'yes'
        Current logged-in user: {user_info}
        When the patient asks about 'my appointments' or 'my details', use their UHID from above. Do not ask for UHID.
        Always use 24-hour format for time (e.g., '22:00' not '10:00 PM').
        When booking at 'earliest' or 'next available', pass preferred_time as empty string. Do NOT guess a time.""")
    messages = [system_msg] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    # print(f"\n[DEBUG] Tool calls: {response.tool_calls}")
    # print(f"[DEBUG] Response: {response.content[:100] if response.content else 'no content'}\n")

    print(f"\n[DEBUG] Tool calls: {response.tool_calls}")
    print(f"[DEBUG] Response: {response.content[:100] if response.content else 'no content'}\n")
    return {"messages": [response]}



def patient_should_continue(state: PatientState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


patient_graph = StateGraph(PatientState)
patient_graph.add_node("patient_chatbot", patient_chatbot)
patient_graph.add_node("tools", ToolNode(patient_tools))
patient_graph.add_edge("tools", "patient_chatbot")
patient_graph.add_conditional_edges("patient_chatbot", patient_should_continue, {"tools": "tools", END: END})
patient_graph.set_entry_point("patient_chatbot")

patient_app = patient_graph.compile()
