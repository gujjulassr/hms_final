import asyncio
from datetime import datetime, date
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from config.settings import DATABASE_URL
from models.session import Session
from models.appointment import Appointment
from models.patient import Patient
import logging
import uuid

logger = logging.getLogger(__name__)

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def auto_complete_expired_sessions():
    """Find active/scheduled sessions that have passed their end time and auto-complete them."""
    async with async_session() as db:
        now = datetime.now().time()

        # Find sessions that should be completed
        result = await db.execute(
            select(Session).where(
                Session.session_date == date.today(),
                Session.status.in_(["active", "scheduled"]),
                Session.end_time < now
            )
        )
        expired_sessions = result.scalars().all()

        for session in expired_sessions:
            # Check if doctor extended (add overtime)
            actual_end = datetime.combine(session.session_date, session.end_time)
            if session.overtime_minutes > 0:
                from datetime import timedelta
                actual_end = actual_end + timedelta(minutes=session.overtime_minutes)
                if actual_end.time() > now:
                    continue  # Session still running with overtime

            # Find next session for propagation
            next_result = await db.execute(
                select(Session).where(
                    Session.doctor_id == session.doctor_id,
                    Session.session_date == date.today(),
                    Session.status == "scheduled",
                    Session.start_time > session.end_time
                ).order_by(Session.start_time)
            )
            next_session = next_result.scalars().first()

            # Process pending appointments
            appt_result = await db.execute(
                select(Appointment, Patient)
                .join(Patient, Appointment.patient_id == Patient.id)
                .where(
                    Appointment.session_id == session.id,
                    Appointment.status.in_(["booked", "checked_in"])
                )
            )
            pending = appt_result.all()

            no_show_count = 0
            cancelled_count = 0
            propagated_count = 0

            for appt, patient in pending:
                if appt.status == "booked":
                    appt.status = "no_show"
                    patient.risk_score += 20
                    no_show_count += 1

                elif appt.status == "checked_in":
                    if next_session:
                        # Propagate to next session
                        new_appt = Appointment(
                            id=uuid.uuid4(),
                            session_id=next_session.id,
                            patient_id=patient.id,
                            booked_by=appt.booked_by,
                            slot_number=1,
                            slot_position=1,
                            slot_time=next_session.start_time,
                            status="checked_in",
                            priority=appt.priority,
                            is_emergency=appt.is_emergency,
                            checked_in_at=appt.checked_in_at
                        )
                        db.add(new_appt)
                        appt.status = "cancelled"
                        propagated_count += 1
                    else:
                        appt.status = "cancelled"
                        cancelled_count += 1

            session.status = "completed"
            await db.commit()
            logger.info(f"Auto-completed session {session.id}: {no_show_count} no-shows, {propagated_count} propagated, {cancelled_count} cancelled")


async def run_scheduler():
    """Run cleanup every 5 minutes."""
    while True:
        try:
            await auto_complete_expired_sessions()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        await asyncio.sleep(300)  # 5 minutes
