from langchain_core.tools import tool
from sqlalchemy import select
from models.appointment import Appointment
from models.patient import Patient
from models.user import User
from models.session import Session
from models.doctor import Doctor
from config.database import AsyncSessionLocal as async_session
from datetime import datetime, date
from services.audit import log_action
from services.notifications.service import notify_checkin, notify_feedback


def get_age_priority(dob):
    """Calculate age-based priority from date of birth."""
    if not dob:
        return 4  # default adult
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age <= 2:
        return 1  # infant
    elif age >= 65:
        return 2  # elderly
    elif age <= 12:
        return 3  # child
    else:
        return 4  # adult


def get_overall_priority(appt_priority, age_priority):
    """Staff-set priority beats age priority. CRITICAL=0, HIGH=1, then age priority."""
    if appt_priority == "CRITICAL":
        return 0
    elif appt_priority == "HIGH":
        return 1
    else:
        return age_priority + 2  # NORMAL: age priority shifted so it's always lower than HIGH


@tool
async def checkin_patient(patient_uhid: str) -> str:
    """Check in a patient who has arrived. Changes status from booked to checked_in."""
    async with async_session() as db:
        result = await db.execute(
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(
                Patient.uhid == patient_uhid,
                Appointment.status == "booked"
            )
        )
        row = result.first()

        if not row:
            return f"No booked appointment found for {patient_uhid}."
        

        appt, patient = row

        # Check if session is active
        sess_result = await db.execute(select(Session).where(Session.id == appt.session_id))
        sess = sess_result.scalars().first()
        if not sess or sess.status != "active":
            return f"Cannot check in — session is not active yet. Current status: {sess.status if sess else 'not found'}."

        
        appt.status = "checked_in"
        appt.checked_in_at = datetime.now()

        await log_action(db, patient.user_id, "CHECKIN", "appointment", appt.id, {"uhid": patient_uhid})

        # Get patient email and doctor name for notification
        pat_user_result = await db.execute(select(User).where(User.id == patient.user_id))
        pat_user = pat_user_result.scalars().first()
        doc_user_result = await db.execute(
            select(User).join(Doctor, Doctor.user_id == User.id).join(Session, Session.doctor_id == Doctor.id).where(Session.id == appt.session_id)
        )
        doc_user = doc_user_result.scalars().first()
        await db.commit()

    if pat_user:
        doc_name = doc_user.full_name if doc_user else "Doctor"
        await notify_checkin(pat_user.email, pat_user.full_name, doc_name, 15)

    return f"Patient {patient_uhid} checked in successfully at {appt.checked_in_at.strftime('%H:%M')}."


@tool
async def get_queue(doctor_name: str) -> str:
    """Get the current queue for a doctor's active session, sorted by slot and priority."""
    async with async_session() as db:
        # Find active or scheduled session for today
        result = await db.execute(
            select(Session, Doctor, User)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(
                User.full_name.ilike(f"%{doctor_name}%"),
                Session.session_date == date.today(),
                Session.status.in_(["active", "scheduled"])
            )
        )
        session_row = result.first()
        if not session_row:
            return f"No active session found for {doctor_name} today."

        session, doctor, doc_user = session_row

        # Get checked_in and in_progress appointments
        appt_result = await db.execute(
            select(Appointment, Patient, User)
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .where(
                Appointment.session_id == session.id,
                Appointment.status.in_(["checked_in", "in_progress"]),
                Appointment.is_emergency == False
            ).order_by(Appointment.slot_number)
        )
        normal_rows = appt_result.all()

        # Get emergency queue
        emerg_result = await db.execute(
            select(Appointment, Patient, User)
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .where(
                Appointment.session_id == session.id,
                Appointment.status.in_(["checked_in", "in_progress"]),
                Appointment.is_emergency == True
            ).order_by(Appointment.checked_in_at)
        )
        emerg_rows = emerg_result.all()

        # Sort normal queue by slot number, then by priority within slot
        sorted_normal = sorted(normal_rows, key=lambda r: (
            r[0].slot_number,
            get_overall_priority(r[0].priority, get_age_priority(r[1].date_of_birth))
        ))

        output = f"--- Queue for Dr. {doc_user.full_name} ---\n\n"

        if emerg_rows:
            output += "EMERGENCY QUEUE:\n"
            for appt, patient, user in emerg_rows:
                output += f"  [{appt.status.upper()}] {patient.uhid} - {user.full_name} (Priority: {appt.priority})\n"
            output += "\n"

        if sorted_normal:
            output += "NORMAL QUEUE:\n"
            current_slot = None
            for appt, patient, user in sorted_normal:
                if appt.slot_number != current_slot:
                    current_slot = appt.slot_number
                    output += f"  Slot {current_slot} ({appt.slot_time}):\n"
                age_p = get_age_priority(patient.date_of_birth)
                age_label = {1: "Infant", 2: "Elderly", 3: "Child", 4: "Adult"}.get(age_p, "Adult")
                output += f"    [{appt.status.upper()}] {patient.uhid} - {user.full_name} ({age_label}, Priority: {appt.priority})\n"
        else:
            output += "NORMAL QUEUE: Empty\n"

        if not emerg_rows and not sorted_normal:
            output += "No patients in queue.\n"

    return output


@tool
async def call_next(doctor_name: str) -> str:
    """Suggest the next patient for the doctor based on slot order and age priority."""
    async with async_session() as db:
        result = await db.execute(
            select(Session, Doctor, User)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(
                User.full_name.ilike(f"%{doctor_name}%"),
                Session.session_date == date.today(),
                Session.status.in_(["active", "scheduled"])
            )
        )
        session_row = result.first()
        if not session_row:
            return f"No active session found for {doctor_name} today."

        session, doctor, doc_user = session_row

        # Get checked_in patients (not yet being seen)
        appt_result = await db.execute(
            select(Appointment, Patient, User)
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .where(
                Appointment.session_id == session.id,
                Appointment.status == "checked_in"
            ).order_by(Appointment.slot_number)
        )
        rows = appt_result.all()

        if not rows:
            return "No patients waiting in the queue."

        # Sort by slot number, then priority
        sorted_patients = sorted(rows, key=lambda r: (
            r[0].slot_number,
            get_overall_priority(r[0].priority, get_age_priority(r[1].date_of_birth))
        ))

        # First patient is the suggestion
        appt, patient, user = sorted_patients[0]
        age_p = get_age_priority(patient.date_of_birth)
        age_label = {1: "Infant", 2: "Elderly", 3: "Child", 4: "Adult"}.get(age_p, "Adult")

    return f"Next patient: {patient.uhid} - {user.full_name} ({age_label}, Slot {appt.slot_number}, Time: {appt.slot_time}, Priority: {appt.priority})"


@tool
async def call_patient(patient_uhid: str) -> str:
    """Doctor calls a specific patient. Changes status from checked_in to in_progress."""
    async with async_session() as db:
        result = await db.execute(
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(
                Patient.uhid == patient_uhid,
                Appointment.status == "checked_in"
            )
        )
        row = result.first()

        if not row:
            return f"No checked-in appointment found for {patient_uhid}."

        appt, patient = row
        appt.status = "in_progress"
        appt.called_at = datetime.now()
        appt.started_at = datetime.now()

        await log_action(db, patient.user_id, "CALL", "appointment", appt.id, {"uhid": patient_uhid})
        await db.commit()

    return f"Patient {patient_uhid} called in. Consultation started at {appt.started_at.strftime('%H:%M')}."


@tool
async def complete_appointment(patient_uhid: str, notes: str = "") -> str:
    """Mark a patient's appointment as completed after consultation."""
    async with async_session() as db:
        result = await db.execute(
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(
                Patient.uhid == patient_uhid,
                Appointment.status == "in_progress"
            )
        )
        row = result.first()

        if not row:
            return f"No in-progress appointment found for {patient_uhid}."

        appt, patient = row
        appt.status = "completed"
        appt.completed_at = datetime.now()
        if notes:
            appt.notes = notes

        # Calculate delay
        sess_result = await db.execute(select(Session).where(Session.id == appt.session_id))
        sess = sess_result.scalars().first()
        if sess and appt.started_at:
            actual_duration = (appt.completed_at - appt.started_at).total_seconds() / 60
            expected_duration = sess.slot_duration_minutes
            if actual_duration > expected_duration:
                extra_delay = int(actual_duration - expected_duration)
                sess.delay_minutes += extra_delay

        await log_action(db, patient.user_id, "COMPLETE", "appointment", appt.id, {"uhid": patient_uhid, "notes": notes})

        # Get patient email and doctor name for feedback notification
        pat_user_result = await db.execute(select(User).where(User.id == patient.user_id))
        pat_user = pat_user_result.scalars().first()
        doc_user_result = await db.execute(
            select(User).join(Doctor, Doctor.user_id == User.id).join(Session, Session.doctor_id == Doctor.id).where(Session.id == appt.session_id)
        )
        doc_user = doc_user_result.scalars().first()
        await db.commit()

    if pat_user:
        doc_name = doc_user.full_name if doc_user else "Doctor"
        await notify_feedback(pat_user.email, pat_user.full_name, doc_name)

    return f"Appointment completed for {patient_uhid} at {appt.completed_at.strftime('%H:%M')}."


@tool
async def emergency_book(patient_uhid: str, doctor_name: str) -> str:
    """Book an emergency appointment. Bypasses normal slots, goes to emergency queue."""
    import uuid
    async with async_session() as db:
        # Find patient
        patient_result = await db.execute(select(Patient).where(Patient.uhid == patient_uhid))
        patient = patient_result.scalars().first()
        if not patient:
            return f"Patient with UHID {patient_uhid} not found."

        # Find doctor's active/scheduled session today
        result = await db.execute(
            select(Session, Doctor, User)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(
                User.full_name.ilike(f"%{doctor_name}%"),
                Session.session_date == date.today(),
                Session.status.in_(["active", "scheduled"])
            )
        )
        session_row = result.first()
        if not session_row:
            return f"No active session found for {doctor_name} today."

        session, doctor, doc_user = session_row

        # Create emergency appointment (slot_number = 0)
        new_appt = Appointment(
            id=uuid.uuid4(),
            session_id=session.id,
            patient_id=patient.id,
            booked_by=patient.user_id,
            slot_number=0,
            slot_position=1,
            slot_time=session.start_time,
            status="checked_in",
            priority="CRITICAL",
            is_emergency=True,
            checked_in_at=datetime.now()
        )
        db.add(new_appt)
        await log_action(db, patient.user_id, "EMERGENCY", "appointment", new_appt.id, {"uhid": patient_uhid, "doctor": doc_user.full_name})
        await db.commit()

    return f"Emergency appointment booked for {patient_uhid} with Dr. {doc_user.full_name}. Patient added to emergency queue."


@tool
async def set_priority(patient_uhid: str, priority: str) -> str:
    """Set priority for a patient's appointment. Priority can be NORMAL, HIGH, or CRITICAL."""
    if priority not in ["NORMAL", "HIGH", "CRITICAL"]:
        return "Invalid priority. Use NORMAL, HIGH, or CRITICAL."

    async with async_session() as db:
        result = await db.execute(
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(
                Patient.uhid == patient_uhid,
                Appointment.status.in_(["booked", "checked_in"])
            )
        )
        row = result.first()

        if not row:
            return f"No active appointment found for {patient_uhid}."

        appt, patient = row
        appt.priority = priority

        await log_action(db, patient.user_id, "SET_PRIORITY", "appointment", appt.id, {"uhid": patient_uhid, "priority": priority})
        await db.commit()

    return f"Priority for {patient_uhid} set to {priority}."


@tool
async def get_my_sessions(doctor_name: str, session_date: str = "") -> str:
    """Get a doctor's sessions. If session_date is empty, shows today. Use YYYY-MM-DD format or 'tomorrow'."""
    from datetime import timedelta
    async with async_session() as db:
        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.full_name.ilike(f"%{doctor_name}%"))
        )
        doc_row = doc_result.first()
        if not doc_row:
            return f"Doctor {doctor_name} not found."
        doctor, doc_user = doc_row

        # Parse date
        if session_date == "tomorrow":
            query_date = date.today() + timedelta(days=1)
        elif session_date:
            try:
                query_date = datetime.strptime(session_date, "%Y-%m-%d").date()
            except ValueError:
                query_date = date.today()
        else:
            query_date = date.today()

        sess_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date == query_date,
                Session.status != "cancelled"
            ).order_by(Session.start_time)
        )
        sessions = sess_result.scalars().all()

    if not sessions:
        return f"No sessions for Dr. {doc_user.full_name} on {query_date}."

    output = f"Sessions for Dr. {doc_user.full_name} on {query_date}:\n\n"
    for s in sessions:
        is_afternoon = s.start_time.hour >= 12
        extendable = " (Extendable)" if is_afternoon and s.status == "active" else ""
        from datetime import timedelta as td
        actual_end = (datetime.combine(s.session_date, s.end_time) + td(minutes=s.overtime_minutes)).time() if s.overtime_minutes > 0 else s.end_time
        output += f"{s.start_time}-{actual_end} | Status: {s.status.upper()} | Slots: {s.total_slots}{extendable}"
        if s.delay_minutes > 0:
            output += f" | Delay: {s.delay_minutes}min"
        output += "\n"
    return output


@tool
async def get_my_patients(doctor_name: str, patient_date: str = "") -> str:
    """Get all patients who have appointments with a doctor. Use YYYY-MM-DD format, 'tomorrow', or empty for today."""
    from datetime import timedelta
    async with async_session() as db:
        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.full_name.ilike(f"%{doctor_name}%"))
        )
        doc_row = doc_result.first()
        if not doc_row:
            return f"Doctor {doctor_name} not found."
        doctor, doc_user = doc_row

        if patient_date == "tomorrow":
            query_date = date.today() + timedelta(days=1)
        elif patient_date:
            try:
                query_date = datetime.strptime(patient_date, "%Y-%m-%d").date()
            except ValueError:
                query_date = date.today()
        else:
            query_date = date.today()

        appt_result = await db.execute(
            select(Appointment, Patient, User, Session)
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .join(Session, Appointment.session_id == Session.id)
            .where(
                Session.doctor_id == doctor.id,
                Session.session_date == query_date
            ).order_by(Appointment.slot_number)
        )
        rows = appt_result.all()

    if not rows:
        return f"No patients found for Dr. {doc_user.full_name} on {query_date}."

    completed = sum(1 for r in rows if r[0].status == "completed")
    cancelled = sum(1 for r in rows if r[0].status == "cancelled")
    no_show = sum(1 for r in rows if r[0].status == "no_show")
    waiting = sum(1 for r in rows if r[0].status in ["booked", "checked_in"])

    emergency_count = sum(1 for r in rows if r[0].is_emergency)

    output = f"Patients for Dr. {doc_user.full_name} on {query_date} (Total: {len(rows)}, Completed: {completed}, Cancelled: {cancelled}, No-show: {no_show}, Waiting: {waiting}, Emergency: {emergency_count}):\n\n"
    for appt, patient, pat_user, session in rows:
        emergency_tag = " [EMERGENCY]" if appt.is_emergency else ""
        priority_tag = f" Priority: {appt.priority}" if appt.priority != "NORMAL" else ""
        checked_in = " (Was checked in)" if appt.checked_in_at else " (Never checked in)"
        output += f"UHID: {patient.uhid}, Name: {pat_user.full_name}, Time: {appt.slot_time}, Status: {appt.status.upper()}{emergency_tag}{priority_tag}{checked_in}\n"
    return output


@tool
async def get_audit_log(limit: int = 20) -> str:
    """View recent audit log entries. Shows who did what and when."""
    from models.audit_log import AuditLog
    async with async_session() as db:
        result = await db.execute(
            select(AuditLog, User)
            .join(User, AuditLog.user_id == User.id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        rows = result.all()

    if not rows:
        return "No audit log entries found."

    output = "--- AUDIT LOG ---\n"
    for log, user in rows:
        details_str = str(log.details) if log.details else ""
        output += f"[{log.created_at.strftime('%Y-%m-%d %H:%M')}] {user.full_name} | {log.action} | {log.target_type} | {details_str}\n"
    return output
