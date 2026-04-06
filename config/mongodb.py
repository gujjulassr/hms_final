from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import MONGODB_URI, MONGODB_DB
from datetime import datetime
import uuid

client = AsyncIOMotorClient(MONGODB_URI)
db = client[MONGODB_DB]
conversations = db["conversations"]


async def save_message(conversation_id, role, sender, content):
    await conversations.insert_one({
        "conversation_id": conversation_id,
        "role": role,
        "sender": sender,
        "content": content,
        "timestamp": datetime.now()
    })


async def get_history(conversation_id):
    cursor = conversations.find(
        {"conversation_id": conversation_id}
    ).sort("timestamp", 1)
    messages = []
    async for doc in cursor:
        messages.append({
            "sender": doc["sender"],
            "content": doc["content"]
        })
    return messages


async def clear_history(conversation_id):
    await conversations.delete_many({"conversation_id": conversation_id})


def new_conversation_id():
    return str(uuid.uuid4())
