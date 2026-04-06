from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from langchain_core.messages import HumanMessage
from agent.graph import app
from config.mongodb import get_user_conversations, save_message, get_history, clear_history, new_conversation_id
from services.auth import decode_token
from sqlalchemy import select
from models.patient import Patient
from models.user import User
from config.database import AsyncSessionLocal as _async_session

router = APIRouter()
security = HTTPBearer()


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str


# Store active conversations in memory for message history
active_conversations = {}


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract user info from JWT token."""
    try:
        payload = decode_token(credentials.credentials)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest, user: dict = Depends(get_current_user)):
    role = user["role"]
    conv_id = request.conversation_id or new_conversation_id()

    if conv_id not in active_conversations:
        active_conversations[conv_id] = []

    messages = active_conversations[conv_id]
    messages.append(HumanMessage(content=request.message))

    await save_message(conv_id, role, "user", request.message, user["email"])

    # Get user info for context
    user_info = f"email: {user['email']}, role: {role}"
    async with _async_session() as db:
        if role == "patient":
            pat_result = await db.execute(
                select(Patient, User).join(User, Patient.user_id == User.id).where(User.email == user["email"])
            )
            pat_row = pat_result.first()
            if pat_row:
                patient, pat_user = pat_row
                user_info = f"UHID: {patient.uhid}, Name: {pat_user.full_name}, Email: {pat_user.email}"
        elif role == "doctor":
            from models.doctor import Doctor
            doc_result = await db.execute(
                select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.email == user["email"])
            )
            doc_row = doc_result.first()
            if doc_row:
                doctor, doc_user = doc_row
                user_info = f"Name: {doc_user.full_name}, Specialization: {doctor.specialization}"

    result = await app.ainvoke({"messages": messages, "role": role, "user_info": user_info})
    messages = result["messages"]
    active_conversations[conv_id] = messages

    bot_reply = messages[-1].content

    await save_message(conv_id, role, "bot", bot_reply, user["email"])

    return ChatResponse(reply=bot_reply, conversation_id=conv_id)


@router.get("/history/{conversation_id}")
async def get_chat_history(conversation_id: str, user: dict = Depends(get_current_user)):
    history = await get_history(conversation_id)
    return {"conversation_id": conversation_id, "messages": history}


@router.post("/clear/{conversation_id}")
async def clear_chat(conversation_id: str, user: dict = Depends(get_current_user)):
    await clear_history(conversation_id)
    if conversation_id in active_conversations:
        del active_conversations[conversation_id]
    return {"message": "Conversation cleared"}


@router.post("/new")
async def new_chat(user: dict = Depends(get_current_user)):
    conv_id = new_conversation_id()
    return {"conversation_id": conv_id}



@router.get("/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):                                                                                                     
    convs = await get_user_conversations(user["email"])
    return {"conversations": convs} 
