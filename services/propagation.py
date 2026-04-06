# services/propagation.py
# Handles session completion
# Rules:
# 1. Booked (never checked in) → no_show, risk +20
# 2. Checked-in (waiting) → stay as checked_in, shown as "propagated" in next session queue
# 3. Doctor sees propagated patients in separate section, decides who to attend
# 4. Only first session propagates, second session doctor extends or cancels

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.session import Session
from models.appointment import Appointment
from models.patient import Patient
from datetime import date


async def complete_session_with_propagation(db: AsyncSession, session: Session):
    """
    Complete a session. Mark no-shows, keep checked-in as propagated.
    Returns summary dict.
    """
    summary = {"no_show": 0, "propagated": 0, "cancelled": 0}

    # Get all pending appointments
    pending_result = await db.execute(
        select(Appointment, Patient)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(
            Appointment.session_id == session.id,
            Appointment.status.in_(["booked", "checked_in"])
        ).order_by(Appointment.slot_number)
    )
    pending = pending_result.all()

    for appt, patient in pending:
        if appt.status == "booked":
            # Never checked in → no_show
            appt.status = "no_show"
            patient.risk_score += 20
            summary["no_show"] += 1
        elif appt.status == "checked_in":
            # Stay as checked_in — will show as propagated in doctor's queue
            # Don't change status, don't move, don't cancel
            summary["propagated"] += 1

    session.status = "completed"
    return summary
