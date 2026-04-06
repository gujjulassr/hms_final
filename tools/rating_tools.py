from langchain_core.tools import tool
from sqlalchemy import select, func
from models.rating import Rating
from models.appointment import Appointment
from models.patient import Patient
from models.doctor import Doctor
from models.user import User
from config.settings import OPENAI_API_KEY
from config.database import AsyncSessionLocal as async_session
from services.audit import log_action
import uuid
from datetime import datetime
import chromadb
from openai import AsyncOpenAI

# ChromaDB for RAG
chroma_client = chromadb.PersistentClient(path="./chroma_db")
reviews_collection = chroma_client.get_or_create_collection(name="doctor_reviews")

# OpenAI for sentiment
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def get_sentiment(review_text):
    """Use OpenAI to calculate sentiment score from -1.0 to 1.0."""
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a sentiment analyzer. Given a review, return ONLY a number between -1.0 (very negative) and 1.0 (very positive). Nothing else, just the number."},
            {"role": "user", "content": review_text}
        ]
    )
    try:
        score = float(response.choices[0].message.content.strip())
        return max(-1.0, min(1.0, score))
    except ValueError:
        return 0.0


@tool
async def submit_rating(patient_uhid: str, doctor_name: str, rating: int, review: str = "") -> str:
    """Submit a rating for a doctor after a completed appointment. Rating 1-5, optional review text."""
    if rating < 1 or rating > 5:
        return "Rating must be between 1 and 5."

    async with async_session() as db:
        # Find patient and doctor
        pat_result = await db.execute(select(Patient).where(Patient.uhid == patient_uhid))
        patient = pat_result.scalars().first()
        if not patient:
            return f"Patient {patient_uhid} not found."

        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.full_name.ilike(f"%{doctor_name}%"))
        )
        doc_row = doc_result.first()
        if not doc_row:
            return f"Doctor {doctor_name} not found."
        doctor, doc_user = doc_row

        # Find completed appointment for this patient with this doctor
        appt_result = await db.execute(
            select(Appointment)
            .where(
                Appointment.patient_id == patient.id,
                Appointment.status == "completed"
            ).order_by(Appointment.completed_at.desc())
        )
        appt = appt_result.scalars().first()
        if not appt:
            return f"No completed appointment found for {patient_uhid}."

        # Check if already rated
        existing = await db.execute(
            select(Rating).where(Rating.appointment_id == appt.id)
        )
        if existing.scalars().first():
            return "This appointment has already been rated."

        # Calculate sentiment if review provided
        sentiment_score = None
        if review:
            sentiment_score = await get_sentiment(review)

        # Create rating
        new_rating = Rating(
            id=uuid.uuid4(),
            appointment_id=appt.id,
            doctor_id=doctor.id,
            patient_id=patient.id,
            rating=rating,
            review=review if review else None,
            sentiment_score=sentiment_score
        )
        db.add(new_rating)

        # Update doctor avg rating
        rating_result = await db.execute(
            select(func.avg(Rating.rating), func.count(Rating.id)).where(Rating.doctor_id == doctor.id)
        )
        avg_row = rating_result.first()
        if avg_row:
            doctor.avg_rating = float(avg_row[0] or rating)
            doctor.total_ratings = (avg_row[1] or 0) + 1

        # Store in ChromaDB for RAG search
        if review:
            reviews_collection.add(
                documents=[review],
                metadatas=[{
                    "doctor_name": doc_user.full_name,
                    "patient_uhid": patient_uhid,
                    "rating": rating,
                    "sentiment": sentiment_score or 0.0,
                    "date": datetime.now().strftime("%Y-%m-%d")
                }],
                ids=[str(new_rating.id)]
            )

        await log_action(db, patient.user_id, "RATE", "rating", new_rating.id, {"doctor": doc_user.full_name, "rating": rating, "sentiment": sentiment_score})
        await db.commit()

    sentiment_text = ""
    if sentiment_score is not None:
        if sentiment_score > 0.3:
            sentiment_text = " (Positive)"
        elif sentiment_score < -0.3:
            sentiment_text = " (Negative)"
        else:
            sentiment_text = " (Neutral)"

    return f"Rating submitted! Doctor: {doc_user.full_name}, Stars: {rating}/5{sentiment_text}"


@tool
async def get_doctor_ratings(doctor_name: str) -> str:
    """Get all ratings and reviews for a doctor."""
    async with async_session() as db:
        result = await db.execute(
            select(Rating, Doctor, User, Patient)
            .join(Doctor, Rating.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .join(Patient, Rating.patient_id == Patient.id)
            .where(User.full_name.ilike(f"%{doctor_name}%"))
            .order_by(Rating.created_at.desc())
        )
        rows = result.all()

    if not rows:
        return f"No ratings found for {doctor_name}."

    # Get doctor info from first row
    _, doctor, doc_user, _ = rows[0]
    output = f"Ratings for Dr. {doc_user.full_name} (Avg: {doctor.avg_rating:.1f}/5, Total: {doctor.total_ratings})\n\n"

    for rating, _, _, patient in rows:
        sentiment = ""
        if rating.sentiment_score is not None:
            if rating.sentiment_score > 0.3:
                sentiment = "Positive"
            elif rating.sentiment_score < -0.3:
                sentiment = "Negative"
            else:
                sentiment = "Neutral"
        output += f"Stars: {rating.rating}/5 | {patient.uhid} | {sentiment}\n"
        if rating.review:
            output += f"  Review: {rating.review}\n"
        output += "\n"
    return output


@tool
async def search_feedback(query: str) -> str:
    """Search patient reviews using semantic search. Example: 'doctor was rude' or 'gentle with children'."""
    results = reviews_collection.query(
        query_texts=[query],
        n_results=5
    )

    if not results["documents"] or not results["documents"][0]:
        return "No matching reviews found."

    output = f"Reviews matching '{query}':\n\n"
    for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
        output += f"{i+1}. Dr. {meta['doctor_name']} | Rating: {meta['rating']}/5 | Sentiment: {meta['sentiment']:.1f}\n"
        output += f"   Review: {doc}\n\n"
    return output
