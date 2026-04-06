from langchain_core.tools import tool
from sqlalchemy import select
from models.doctor import Doctor
from models.user import User
from config.database import AsyncSessionLocal as async_session


@tool
async def search_doctors(query: str) -> str:
    """Search doctors by name or specialization. Use empty string to list all doctors."""
    async with async_session() as db:
        stmt = select(Doctor, User).join(User, Doctor.user_id == User.id).where(
            (User.full_name.ilike(f"%{query}%")) | (Doctor.specialization.ilike(f"%{query}%"))
        )
        result = await db.execute(stmt)
        rows = result.all()

    if not rows:
        return "No doctors found."

    output = ""
    for doctor, user in rows:
        output += f"Name: {user.full_name}, Specialization: {doctor.specialization}, Fee: {doctor.consultation_fee}, Rating: {doctor.avg_rating}\n"
    return output
