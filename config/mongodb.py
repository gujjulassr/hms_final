from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import MONGODB_URI, MONGODB_DB
from datetime import datetime
import uuid

client = AsyncIOMotorClient(MONGODB_URI)
db = client[MONGODB_DB]
conversations = db["conversations"]


# async def save_message(conversation_id, role, sender, content):
#     await conversations.insert_one({
#         "conversation_id": conversation_id,
#         "role": role,
#         "sender": sender,
#         "content": content,
#         "timestamp": datetime.now()
#     })


async def save_message(conversation_id, role, sender, content, user_email=""):                                                                                            
      await conversations.insert_one({
          "conversation_id": conversation_id,                                                                                                                               
          "role": role,
          "sender": sender,                                                                                                                                                 
          "content": content,
          "user_email": user_email,
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



async def get_user_conversations(user_email):                                                                                                                             
      pipeline = [
          {"$match": {"user_email": user_email}},
          {"$group": {"_id": "$conversation_id", "last_message": {"$last": "$content"}, "timestamp": {"$last": "$timestamp"}}},
          {"$sort": {"timestamp": -1}},                                                                                                                                     
          {"$limit": 10}                                                                                                                                                    
      ]                                                                                                                                                                     
      result = []                                                                                                                                                           
      async for doc in conversations.aggregate(pipeline):
          result.append({"id": doc["_id"], "preview": doc["last_message"][:50], "time": doc["timestamp"]})
      return result   


async def clear_history(conversation_id):
    await conversations.delete_many({"conversation_id": conversation_id})


def new_conversation_id():
    return str(uuid.uuid4())
