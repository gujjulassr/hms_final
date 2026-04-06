from typing import Annotated, TypedDict, Optional
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from agent.patient_agent import patient_app
from agent.doctor_agent import doctor_app
from agent.staff_agent import staff_app
from langgraph.checkpoint.memory import MemorySaver   




memory = MemorySaver()
# app = graph.compile(checkpointer=memory)


class SupervisorState(TypedDict):
    messages: Annotated[list, add_messages]
    role: str
    user_info: str


async def route_to_agent(state: SupervisorState):
    role = state.get("role", "patient")
    messages = state["messages"]
    user_info = state.get("user_info", "")

    if role == "doctor":
        result = await doctor_app.ainvoke({"messages": messages, "user_info": user_info})
    elif role in ["nurse", "staff", "admin"]:
        result = await staff_app.ainvoke({"messages": messages, "user_info": user_info})
    else:
        result = await patient_app.ainvoke({"messages": messages, "user_info": user_info})

    return {"messages": result["messages"]}


graph = StateGraph(SupervisorState)
graph.add_node("supervisor", route_to_agent)
graph.set_entry_point("supervisor")
graph.add_edge("supervisor", END)

app = graph.compile(checkpointer=memory)
