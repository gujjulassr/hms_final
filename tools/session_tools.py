from langchain_core.tools import tool
from sqlalchemy import select
from models.session import Session
from models.appointment import Appointment
from models.patient import Patient
from models.doctor import Doctor
from models.user import User
from config.database import AsyncSessionLocal as async_session
import uuid
from datetime import datetime, date, time, timedelta
from services.audit import log_action


@tool
async def check_availability(doctor_name: str, check_date: str = "") -> str:
    """Check available sessions for a doctor. Use check_date as 'today', 'tomorrow', or 'YYYY-MM-DD'. Empty shows all future."""
    async with async_session() as db:
        if check_date == "today":
            query_date = date.today()
        elif check_date == "tomorrow":
            query_date = date.today() + timedelta(days=1)
        elif check_date:
            try:
                query_date = datetime.strptime(check_date, "%Y-%m-%d").date()
            except ValueError:
                query_date = None
        else:
            query_date = None

        stmt = select(Session, Doctor, User).join(Doctor, Session.doctor_id == Doctor.id).join(User, Doctor.user_id == User.id).where(
            User.full_name.ilike(f"%{doctor_name}%"),
            Session.status.in_(["scheduled", "active"])
        )

        if query_date:
            stmt = stmt.where(Session.session_date == query_date)
        else:
            stmt = stmt.where(Session.session_date >= date.today())

        result = await db.execute(stmt)
        rows = result.all()

    if not rows:
        return f"No available sessions found for {doctor_name}."

    output = ""
    for session, doctor, user in rows:
        actual_end = (datetime.combine(session.session_date, session.end_time) + timedelta(minutes=session.overtime_minutes)).time() if session.overtime_minutes > 0 else session.end_time
        output += f"Doctor: {user.full_name}, Date: {session.session_date}, Time: {session.start_time}-{actual_end}, Slots: {session.total_slots}, Slot Duration: {session.slot_duration_minutes}min\n"
    return output


@tool
async def create_session(doctor_name: str, session_date: str, start_time: str, end_time: str, slot_duration: int = 15, max_per_slot: int = 2) -> str:
    """Create a new session for a doctor. Date format: YYYY-MM-DD, Time format: HH:MM."""
    async with async_session() as db:
        # Find doctor
        result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.full_name.ilike(f"%{doctor_name}%"))
        )
        row = result.first()
        if not row:
            return f"Doctor {doctor_name} not found."
        doctor, doc_user = row

        # Parse date and times
        try:
            s_date = datetime.strptime(session_date, "%Y-%m-%d").date()
            s_start = datetime.strptime(start_time, "%H:%M").time()
            s_end = datetime.strptime(end_time, "%H:%M").time()
        except ValueError:
            return "Invalid date or time format. Use YYYY-MM-DD for date and HH:MM for time."

        if s_date < date.today():
            return "Cannot create session in the past."
        

        # Check duplicate                                                                                                                                                 
        existing = await db.execute(                                                                                                                                      
              select(Session).where(
                  Session.doctor_id == doctor.id,
                  Session.session_date == s_date,
                  Session.status != "cancelled"
              )                                                                                                                                                             
          )
        for es in existing.scalars().all():                                                                                                                               
            # Same morning or same afternoon
            both_morning = s_start.hour < 12 and es.start_time.hour < 12
            both_afternoon = s_start.hour >= 12 and es.start_time.hour >= 12                                                                                              
            if both_morning or both_afternoon:
                return f"Dr. {doc_user.full_name} already has a session on {s_date} from {es.start_time}-{es.end_time}." 

        # Calculate total slots
        start_dt = datetime.combine(s_date, s_start)
        end_dt = datetime.combine(s_date, s_end)
        total_minutes = (end_dt - start_dt).total_seconds() / 60
        total_slots = int(total_minutes // slot_duration)

        new_session = Session(
            id=uuid.uuid4(),
            doctor_id=doctor.id,
            session_date=s_date,
            start_time=s_start,
            end_time=s_end,
            slot_duration_minutes=slot_duration,
            max_per_slot=max_per_slot,
            total_slots=total_slots,
            status="scheduled"
        )
        db.add(new_session)
        await log_action(db, doc_user.id, "CREATE_SESSION", "session", new_session.id, {"doctor": doc_user.full_name, "date": str(s_date)})
        await db.commit()

    return f"Session created for Dr. {doc_user.full_name} on {s_date}, {s_start}-{s_end}, {total_slots} slots."


@tool
async def activate_session(doctor_name: str) -> str:
    """Activate a doctor's scheduled session for today. Picks the session closest to current time."""
    async with async_session() as db:
        now = datetime.now().time()
        result = await db.execute(
            select(Session, Doctor, User)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(
                User.full_name.ilike(f"%{doctor_name}%"),
                Session.session_date == date.today(),
                Session.status == "scheduled",
                Session.end_time > now
            ).order_by(Session.start_time)
        )
        row = result.first()
        if not row:
            return f"No scheduled session found for {doctor_name} today."

        session, doctor, doc_user = row
        session.status = "active"
        await log_action(db, doc_user.id, "ACTIVATE_SESSION", "session", session.id, {"doctor": doc_user.full_name})
        await db.commit()

    return f"Session activated for Dr. {doc_user.full_name} ({session.start_time}-{session.end_time})."


@tool
async def complete_session(doctor_name: str) -> str:
    """Complete a doctor's active session. Marks no-shows, cancels uncalled patients, and propagates checked-in patients to next session if available."""
    async with async_session() as db:
        # Find active session
        result = await db.execute(
            select(Session, Doctor, User)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(
                User.full_name.ilike(f"%{doctor_name}%"),
                Session.session_date == date.today(),
                Session.status == "active"
            )
        )
        row = result.first()
        if not row:
            return f"No active session found for {doctor_name} today."

        session, doctor, doc_user = row

        # Get all pending appointments
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

        # Find next session for propagation (same doctor, same day, later time)
        next_session_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date == date.today(),
                Session.status == "scheduled",
                Session.start_time > session.end_time
            ).order_by(Session.start_time)
        )
        next_session = next_session_result.scalars().first()

        from services.notifications.service import notify_no_show
        for appt, patient in pending:
            if appt.status == "booked":
                # Never checked in → no_show
                appt.status = "no_show"
                patient.risk_score += 20
                await log_action(db, patient.user_id, "NO_SHOW", "appointment", appt.id, {"risk_score": patient.risk_score})
                no_show_count += 1
                # Send no-show notification
                pat_user_r = await db.execute(select(User).where(User.id == patient.user_id))
                pat_user = pat_user_r.scalars().first()
                if pat_user:
                    await notify_no_show(pat_user.email, pat_user.full_name, doc_user.full_name, patient.risk_score)

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
                    # No next session → cancel
                    appt.status = "cancelled"
                    cancelled_count += 1

        session.status = "completed"
        await log_action(db, doc_user.id, "COMPLETE_SESSION", "session", session.id, {"no_shows": no_show_count, "propagated": propagated_count, "cancelled": cancelled_count})
        await db.commit()

    summary = f"Session completed for Dr. {doc_user.full_name}.\n"
    summary += f"No-shows: {no_show_count} (risk +20 each)\n"
    summary += f"Propagated to next session: {propagated_count}\n"
    summary += f"Cancelled: {cancelled_count}"
    return summary


@tool
async def extend_session(doctor_name: str, new_end_time: str) -> str:
    # """Extend a doctor's active afternoon session by adding overtime minutes. Only works for today's active session."""
    """
        Extend a doctor's active afternoon session. Provide new end time like '21:00'.
    """


    async with async_session() as db:
        result = await db.execute(
            select(Session, Doctor, User)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(
                User.full_name.ilike(f"%{doctor_name}%"),
                Session.session_date == date.today(),
                Session.status == "active"
            )
        )
        row = result.first()
        if not row:
            return f"No active session found for {doctor_name} today."

        session, doctor, doc_user = row

        # Only allow extending afternoon sessions (start_time >= 12:00)
        if session.start_time < time(12, 0):
            return "Only afternoon sessions can be extended. Morning sessions cannot be extended."

        # Check extension doesn't go past midnight
        # new_end = datetime.combine(session.session_date, session.end_time) + timedelta(minutes=session.overtime_minutes + overtime)
        # new_end = datetime.combine(session.session_date, session.end_time) + timedelta(minutes=overtime) 
        # if new_end.date() > session.session_date:
        #     return "Cannot extend session beyond today. Maximum extension reached."

        # session.overtime_minutes = extra_minutes

        new_end = datetime.strptime(new_end_time, "%H:%M").time()                                                                                                                 
        original_end = session.end_time
        overtime = (datetime.combine(session.session_date, new_end) - datetime.combine(session.session_date, original_end)).total_seconds() / 60                                  
        

        if overtime <= 0:                                                                                                                                                 
              return f"New end time must be after original end time ({original_end})."
        if new_end >= time(0, 0) and new_end < session.start_time:                                                                                                        
            return "Cannot extend past midnight."     

        session.overtime_minutes = int(overtime)                                                                                                                    
                                                       

        # # Add extra slots
        # extra_slots = extra_minutes // session.slot_duration_minutes
        # session.total_slots += extra_slots

        # Recalculate total slots from original session duration + overtime
        original_minutes = (datetime.combine(session.session_date, session.end_time) - datetime.combine(session.session_date, session.start_time)).total_seconds() / 60
        session.total_slots = int((original_minutes + overtime) // session.slot_duration_minutes)

        await log_action(db, doc_user.id, "EXTEND_SESSION", "session", session.id, {"overtime": overtime, "total_overtime": session.overtime_minutes})
        await db.commit()

    new_end = datetime.combine(session.session_date, session.end_time) + timedelta(minutes=session.overtime_minutes)
    # return f"Session extended for Dr. {doc_user.full_name}. Overtime: {session.overtime_minutes} min. {overtime} extra slots added. New end time: {new_end.time()}."

    return f"Session extended for Dr. {doc_user.full_name}. New end time: {new_end}."

@tool
async def cancel_session(doctor_name: str) -> str:
    """Cancel a doctor's scheduled session. All appointments will be cancelled."""
    async with async_session() as db:
        result = await db.execute(
            select(Session, Doctor, User)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(
                User.full_name.ilike(f"%{doctor_name}%"),
                Session.status == "scheduled"
            ).order_by(Session.session_date)
        )
        row = result.first()
        if not row:
            return f"No scheduled session found for {doctor_name}."

        session, doctor, doc_user = row

        # Cancel all appointments in this session
        appt_result = await db.execute(
            select(Appointment).where(
                Appointment.session_id == session.id,
                Appointment.status.in_(["booked", "checked_in"])
            )
        )
        appts = appt_result.scalars().all()
        cancelled_count = 0
        from services.notifications.service import notify_session_cancelled
        for appt in appts:
            appt.status = "cancelled"
            cancelled_count += 1
            # Notify patient about session cancellation
            pat_result = await db.execute(
                select(Patient, User).join(User, Patient.user_id == User.id).where(Patient.id == appt.patient_id)
            )
            pat_row = pat_result.first()
            if pat_row:
                pat, pat_user = pat_row
                await notify_session_cancelled(pat_user.email, pat_user.full_name, doc_user.full_name, str(session.session_date))

        session.status = "cancelled"
        await log_action(db, doc_user.id, "CANCEL_SESSION", "session", session.id, {"doctor": doc_user.full_name, "cancelled_appointments": cancelled_count})
        await db.commit()

    return f"Session cancelled for Dr. {doc_user.full_name} on {session.session_date}. {cancelled_count} appointments cancelled."
