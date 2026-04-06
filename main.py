import asyncio
from langchain_core.messages import HumanMessage, AIMessage
from agent.graph import app
from config.mongodb import save_message, get_history, clear_history, new_conversation_id


async def chat():
    print("HMS Chatbot Ready!")
    print("Roles: patient, doctor, nurse, admin")
    role = input("Enter your role: ").strip().lower()
    if role not in ["patient", "doctor", "nurse", "staff", "admin"]:
        role = "patient"

    conv_id = new_conversation_id()
    print(f"\nLogged in as: {role}. Type 'quit' to exit, 'clear' to reset.\n")

    messages = []
    while True:
        user_input = input("You: ")

        if user_input.lower() == "quit":
            break
        if user_input.lower() == "clear":
            await clear_history(conv_id)
            messages = []
            print("Conversation cleared.\n")
            continue

        messages.append(HumanMessage(content=user_input))
        await save_message(conv_id, role, "user", user_input)

        result = await app.ainvoke({"messages": messages, "role": role})
        messages = result["messages"]
        bot_reply = messages[-1].content

        await save_message(conv_id, role, "bot", bot_reply)
        print(f"Bot: {bot_reply}\n")


asyncio.run(chat())
