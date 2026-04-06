from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select, func
from models.appointment import Appointment
from models.patient import Patient
from models.session import Session
from models.doctor import Doctor
from models.user import User
from config.database import AsyncSessionLocal as async_session
from services.auth import decode_token
from datetime import date, datetime,timedelta

router = APIRouter()
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return decode_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/my-sessions")
async def get_my_sessions(user: dict = Depends(get_current_user)):
    """Get logged-in doctor's sessions for today and future."""
    async with async_session() as db:
        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.email == user["email"])
        )
        doc_row = doc_result.first()
        if not doc_row:
            return {"error": "Doctor not found", "sessions": []}
        doctor, doc_user = doc_row

        session_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date >= date.today(),
                Session.status != "cancelled"
            ).order_by(Session.session_date, Session.start_time)
        )
        sessions = session_result.scalars().all()

        session_list = []
        for sess in sessions:
            appt_result = await db.execute(
                select(func.count(Appointment.id)).where(
                    Appointment.session_id == sess.id,
                    Appointment.status != "cancelled"
                )
            )
            booked = appt_result.scalar() or 0

            actual_end=sess.end_time

            

            session_list.append({
                "id": str(sess.id),
                "date": str(sess.session_date),
                "start_time": str(sess.start_time),
                "end_time": str(sess.end_time),
                "status": sess.status,
                "total_slots": sess.total_slots,
                "booked": booked,
                "delay_minutes": sess.delay_minutes,
                "overtime_minutes": sess.overtime_minutes,
                
            })

    return {"doctor": doc_user.full_name, "sessions": session_list}


@router.get("/queue")
async def get_doctor_queue(doctor_name: str = "", user: dict = Depends(get_current_user)):
    """Get queue for a doctor's active session. If doctor_name is empty, uses logged-in doctor."""
    async with async_session() as db:
        if doctor_name:
            doc_result = await db.execute(
                select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.full_name.ilike(f"%{doctor_name}%"))
            )
        else:
            doc_result = await db.execute(
                select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.email == user["email"])
            )
        doc_row = doc_result.first()
        if not doc_row:
            return {"doctor": "", "session_active": False, "normal_queue": [], "emergency_queue": [], "booked_queue": []}
        doctor, doc_user = doc_row

        # Find active or scheduled session for today
        sess_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date == date.today(),
                Session.status.in_(["active", "scheduled"])
            ).order_by(Session.start_time)
        )
        session = sess_result.scalars().first()
        if not session:
            return {"doctor": doc_user.full_name, "session_active": False, "normal_queue": [], "emergency_queue": [], "booked_queue": []}

        # Normal queue
        normal_result = await db.execute(
            select(Appointment, Patient, User)
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .where(
                Appointment.session_id == session.id,
                Appointment.status.in_(["checked_in", "in_progress"]),
                Appointment.is_emergency == False
            ).order_by(Appointment.slot_number, Appointment.slot_position)
        )
        normal_rows = normal_result.all()

        # Emergency queue
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

        def age_label(dob):
            if not dob:
                return "Adult"
            age = date.today().year - dob.year - ((date.today().month, date.today().day) < (dob.month, dob.day))
            if age <= 2: return "Infant"
            elif age >= 65: return "Elderly"
            elif age <= 12: return "Child"
            return "Adult"

        normal_queue = []
        for appt, patient, pat_user in normal_rows:
            normal_queue.append({
                "uhid": patient.uhid,
                "name": pat_user.full_name,
                "slot": appt.slot_number,
                "position": appt.slot_position,
                "time": str(appt.slot_time),
                "status": appt.status,
                "priority": appt.priority,
                "age_group": age_label(patient.date_of_birth),
                "checked_in_at": str(appt.checked_in_at) if appt.checked_in_at else ""
            })

        emergency_queue = []
        for appt, patient, pat_user in emerg_rows:
            emergency_queue.append({
                "uhid": patient.uhid,
                "name": pat_user.full_name,
                "status": appt.status,
                "priority": appt.priority,
                "age_group": age_label(patient.date_of_birth),
                "checked_in_at": str(appt.checked_in_at) if appt.checked_in_at else ""
            })

        # Booked patients (not yet checked in)
        booked_result = await db.execute(
            select(Appointment, Patient, User)
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .where(
                Appointment.session_id == session.id,
                Appointment.status == "booked"
            ).order_by(Appointment.slot_number)
        )
        booked_rows = booked_result.all()

        booked_queue = []
        for appt, patient, pat_user in booked_rows:
            booked_queue.append({
                "uhid": patient.uhid,
                "name": pat_user.full_name,
                "slot": appt.slot_number,
                "time": str(appt.slot_time),
                "age_group": age_label(patient.date_of_birth)
            })

    return {
        "doctor": doc_user.full_name,
        "session_active": session.status == "active",
        "session_status": session.status,
        "session_time": f"{session.start_time}-{session.end_time}",
        "normal_queue": normal_queue,
        "emergency_queue": emergency_queue,
        "booked_queue": booked_queue
    }


class ActionRequest(BaseModel):
    patient_uhid: str = ""
    notes: str = ""
    priority: str = ""
    extra_minutes: int = 0
    session_id: str = ""


@router.post("/activate-session")
async def activate_session_api(request: ActionRequest = None, user: dict = Depends(get_current_user)):
    """Activate a session. Use session_id for admin, or auto-detect for doctor."""
    import uuid as uuid_lib
    async with async_session() as db:
        session = None

        # If session_id provided (admin), find directly
        if request and request.session_id:
            sess_result = await db.execute(
                select(Session).where(Session.id == uuid_lib.UUID(request.session_id), Session.status == "scheduled")
            )
            session = sess_result.scalars().first()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found or not scheduled.")
            session.status = "active"
            await db.commit()
            return {"message": f"Session activated: {session.start_time}-{session.end_time}"}

        # Otherwise find by logged-in doctor
        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.email == user["email"])
        )
        doc_row = doc_result.first()
        if not doc_row:
            raise HTTPException(status_code=404, detail="Doctor not found")
        doctor, doc_user = doc_row

        now = datetime.now().time()
        sess_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date == date.today(),
                Session.status == "scheduled",
                Session.end_time > now
            ).order_by(Session.start_time)
        )
        session = sess_result.scalars().first()
        if not session:
            # Check if there are completed/past sessions
            past_result = await db.execute(
                select(Session).where(
                    Session.doctor_id == doctor.id,
                    Session.session_date == date.today()
                )
            )
            past_sessions = past_result.scalars().all()
            if past_sessions:
                statuses = [s.status for s in past_sessions]
                if all(s in ["completed", "cancelled"] for s in statuses):
                    raise HTTPException(status_code=400, detail="All sessions for today are already completed. No session to activate.")
                elif any(s == "active" for s in statuses):
                    raise HTTPException(status_code=400, detail="You already have an active session running.")
            raise HTTPException(status_code=404, detail="No scheduled session found for today. Create one first.")

        session.status = "active"
        await db.commit()

    return {"message": f"Session activated: {session.start_time}-{session.end_time}"}


@router.post("/complete-session")
async def complete_session_api(user: dict = Depends(get_current_user)):
    """Complete doctor's active session. Handles no-shows and propagation."""
    import uuid as uuid_lib
    async with async_session() as db:
        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.email == user["email"])
        )
        doc_row = doc_result.first()
        if not doc_row:
            raise HTTPException(status_code=404, detail="Doctor not found")
        doctor, doc_user = doc_row

        sess_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date == date.today(),
                Session.status == "active"
            )
        )
        session = sess_result.scalars().first()
        if not session:
            raise HTTPException(status_code=400, detail="No active session to complete. All sessions may already be completed.")

        # Find next session for propagation
        next_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date == date.today(),
                Session.status == "scheduled",
                Session.start_time > session.end_time
            ).order_by(Session.start_time)
        )
        next_session = next_result.scalars().first()

        appt_result = await db.execute(
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(Appointment.session_id == session.id, Appointment.status.in_(["booked", "checked_in"]))
        )
        pending = appt_result.all()

        no_show = 0
        cancelled = 0
        propagated = 0
        for appt, patient in pending:
            if appt.status == "booked":
                appt.status = "no_show"
                patient.risk_score += 20
                no_show += 1
            elif appt.status == "checked_in":
                if next_session:
                    new_appt = Appointment(
                        id=uuid_lib.uuid4(), session_id=next_session.id, patient_id=patient.id,
                        booked_by=appt.booked_by, slot_number=1, slot_position=1,
                        slot_time=next_session.start_time, status="checked_in",
                        priority=appt.priority, is_emergency=appt.is_emergency, checked_in_at=appt.checked_in_at
                    )
                    db.add(new_appt)
                    appt.status = "cancelled"
                    propagated += 1
                else:
                    appt.status = "cancelled"
                    cancelled += 1

        session.status = "completed"
        await db.commit()

    return {"message": f"Session completed. No-shows: {no_show}, Propagated: {propagated}, Cancelled: {cancelled}"}


@router.post("/extend-session")
async def extend_session_api(request: ActionRequest, user: dict = Depends(get_current_user)):
    """Extend active afternoon session."""
    from datetime import time, timedelta
    import uuid as uuid_lib
    async with async_session() as db:
        session = None

        # If session_id provided (from admin dashboard), find directly
        if request.session_id:
            sess_result = await db.execute(
                select(Session).where(Session.id == uuid_lib.UUID(request.session_id), Session.status == "active")
            )
            session = sess_result.scalars().first()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found or not active.")
        else:
            # Find by logged-in doctor
            doc_result = await db.execute(
                select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.email == user["email"])
            )
            doc_row = doc_result.first()
            if not doc_row:
                raise HTTPException(status_code=404, detail="Doctor not found")
            doctor, doc_user = doc_row

            sess_result = await db.execute(
                select(Session).where(
                    Session.doctor_id == doctor.id,
                    Session.session_date == date.today(),
                    Session.status == "active"
                )
            )
            session = sess_result.scalars().first()

        if not session:
            all_sess = await db.execute(
                select(Session).where(Session.doctor_id == doctor.id, Session.session_date == date.today())
            )
            all_sessions = all_sess.scalars().all()
            if any(s.status == "completed" for s in all_sessions):
                raise HTTPException(status_code=400, detail="Cannot extend — session is already completed.")
            raise HTTPException(status_code=404, detail="No active session to extend. Activate a session first.")

        if session.start_time < time(12, 0):
            raise HTTPException(status_code=400, detail="Only afternoon sessions can be extended. Morning sessions cannot be extended.")

        # new_end = datetime.combine(session.session_date, session.end_time) + timedelta(minutes=session.overtime_minutes + request.extra_minutes)
        new_end = datetime.combine(session.session_date, session.end_time) + timedelta(minutes=request.extra_minutes)                                                             

        if new_end.date() > session.session_date:
            raise HTTPException(status_code=400, detail="Cannot extend beyond today")

        session.overtime_minutes = request.extra_minutes
        # Recalculate total slots from original session duration + overtime
        original_minutes = (datetime.combine(session.session_date, session.end_time) - datetime.combine(session.session_date, session.start_time)).total_seconds() / 60
        session.total_slots = int((original_minutes + request.extra_minutes) // session.slot_duration_minutes)
        await db.commit()

        actual_end = (datetime.combine(session.session_date, session.end_time) + timedelta(minutes=request.extra_minutes)).time()

    return {"message": f"Session extended to {actual_end}. Total slots: {session.total_slots}."}


@router.post("/call-patient")
async def call_patient_api(request: ActionRequest, user: dict = Depends(get_current_user)):
    """Doctor calls a specific patient."""
    async with async_session() as db:
        result = await db.execute(
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(Patient.uhid == request.patient_uhid, Appointment.status == "checked_in")
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"No checked-in patient {request.patient_uhid}")

        appt, patient = row
        appt.status = "in_progress"
        appt.called_at = datetime.now()
        appt.started_at = datetime.now()
        await db.commit()

    return {"message": f"Patient {request.patient_uhid} called in."}


@router.post("/complete-patient")
async def complete_patient_api(request: ActionRequest, user: dict = Depends(get_current_user)):
    """Complete a patient's appointment."""
    async with async_session() as db:
        result = await db.execute(
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(Patient.uhid == request.patient_uhid, Appointment.status == "in_progress")
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"No in-progress appointment for {request.patient_uhid}")

        appt, patient = row
        appt.status = "completed"
        appt.completed_at = datetime.now()
        if request.notes:
            appt.notes = request.notes

        # Calculate delay
        session = await db.execute(select(Session).where(Session.id == appt.session_id))
        sess = session.scalars().first()
        if sess and appt.started_at:
            actual_duration = (appt.completed_at - appt.started_at).total_seconds() / 60
            expected_duration = sess.slot_duration_minutes
            if actual_duration > expected_duration:
                extra_delay = int(actual_duration - expected_duration)
                sess.delay_minutes += extra_delay

        await db.commit()

    return {"message": f"Appointment completed for {request.patient_uhid}."}


@router.post("/set-priority")
async def set_priority_api(request: ActionRequest, user: dict = Depends(get_current_user)):
    """Set priority for a patient."""
    if request.priority not in ["NORMAL", "HIGH", "CRITICAL"]:
        raise HTTPException(status_code=400, detail="Invalid priority")

    async with async_session() as db:
        result = await db.execute(
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(Patient.uhid == request.patient_uhid, Appointment.status.in_(["booked", "checked_in"]))
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"No active appointment for {request.patient_uhid}")

        appt, patient = row
        appt.priority = request.priority
        await db.commit()

    return {"message": f"Priority set to {request.priority} for {request.patient_uhid}."}


@router.post("/checkin-patient")
async def checkin_patient_api(request: ActionRequest, user: dict = Depends(get_current_user)):
    """Check in a patient (nurse/staff action)."""
    async with async_session() as db:
        result = await db.execute(
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(Patient.uhid == request.patient_uhid, Appointment.status == "booked")
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"No booked appointment for {request.patient_uhid}")

        appt, patient = row

        # Check if session is active
        sess_result = await db.execute(select(Session).where(Session.id == appt.session_id))
        sess = sess_result.scalars().first()
        if not sess or sess.status != "active":
            raise HTTPException(status_code=400, detail=f"Cannot check in — session is not active. Current status: {sess.status if sess else 'not found'}.")

        appt.status = "checked_in"
        appt.checked_in_at = datetime.now()
        await db.commit()

    return {"message": f"Patient {request.patient_uhid} checked in at {appt.checked_in_at.strftime('%H:%M')}."}


class CancelSessionRequest(BaseModel):
    session_id: str


@router.post("/cancel-session")
async def cancel_session_api(request: CancelSessionRequest, user: dict = Depends(get_current_user)):
    """Cancel a specific session by ID."""
    import uuid as uuid_lib
    async with async_session() as db:
        try:
            sess_id = uuid_lib.UUID(request.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session ID")

        sess_result = await db.execute(
            select(Session).where(Session.id == sess_id, Session.status.in_(["scheduled", "active"]))
        )
        session = sess_result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or already completed/cancelled.")

        # Cancel all appointments
        appt_result = await db.execute(
            select(Appointment).where(
                Appointment.session_id == session.id,
                Appointment.status.in_(["booked", "checked_in"])
            )
        )
        appts = appt_result.scalars().all()
        cancelled_count = 0
        for appt in appts:
            appt.status = "cancelled"
            cancelled_count += 1

        session.status = "cancelled"
        await db.commit()

    return {"message": f"Session cancelled. {cancelled_count} appointments cancelled."}


class EmergencyRequest(BaseModel):
    patient_uhid: str
    doctor_name: str


@router.post("/emergency-book")
async def emergency_book_api(request: EmergencyRequest, user: dict = Depends(get_current_user)):
    """Emergency booking — bypasses slots, goes to emergency queue."""
    import uuid as uuid_lib
    async with async_session() as db:
        pat_result = await db.execute(select(Patient).where(Patient.uhid == request.patient_uhid))
        patient = pat_result.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {request.patient_uhid} not found")

        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.full_name.ilike(f"%{request.doctor_name}%"))
        )
        doc_row = doc_result.first()
        if not doc_row:
            raise HTTPException(status_code=404, detail=f"Doctor {request.doctor_name} not found")
        doctor, doc_user = doc_row

        sess_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date == date.today(),
                Session.status.in_(["active", "scheduled"])
            )
        )
        session = sess_result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="No active session found")

        new_appt = Appointment(
            id=uuid_lib.uuid4(), session_id=session.id, patient_id=patient.id,
            booked_by=patient.user_id, slot_number=0, slot_position=1,
            slot_time=session.start_time, status="checked_in",
            priority="CRITICAL", is_emergency=True, checked_in_at=datetime.now()
        )
        db.add(new_appt)
        await db.commit()

    return {"message": f"Emergency booking done for {request.patient_uhid} with {doc_user.full_name}."}


class CreateSessionRequest(BaseModel):
    session_date: str
    start_time: str
    end_time: str
    slot_duration: int = 15
    max_per_slot: int = 2


@router.post("/create-session")
async def create_session_api(request: CreateSessionRequest, user: dict = Depends(get_current_user)):
    """Create a new session for the logged-in doctor."""
    import uuid as uuid_lib
    from datetime import timedelta
    async with async_session() as db:
        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.email == user["email"])
        )
        doc_row = doc_result.first()
        if not doc_row:
            raise HTTPException(status_code=404, detail="Doctor not found")
        doctor, doc_user = doc_row

        try:
            s_date = datetime.strptime(request.session_date, "%Y-%m-%d").date()
            s_start = datetime.strptime(request.start_time, "%H:%M").time()
            s_end = datetime.strptime(request.end_time, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date/time format")

        if s_date < date.today():
            raise HTTPException(status_code=400, detail="Cannot create session in the past.")

        if s_date == date.today() and s_end <= datetime.now().time():
            raise HTTPException(status_code=400, detail=f"Cannot create session — {s_end} has already passed today.")

        if s_start >= s_end:
            raise HTTPException(status_code=400, detail="Start time must be before end time.")

        # Check for overlapping sessions
        overlap = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date == s_date,
                Session.status != "cancelled",
                Session.start_time < s_end,
                Session.end_time > s_start
            )
        )
        if overlap.scalars().first():
            raise HTTPException(status_code=400, detail=f"Session already exists for {s_date} that overlaps with {s_start}-{s_end}")

        total_minutes = (datetime.combine(s_date, s_end) - datetime.combine(s_date, s_start)).total_seconds() / 60
        total_slots = int(total_minutes // request.slot_duration)

        new_session = Session(
            id=uuid_lib.uuid4(), doctor_id=doctor.id, session_date=s_date,
            start_time=s_start, end_time=s_end, slot_duration_minutes=request.slot_duration,
            max_per_slot=request.max_per_slot, total_slots=total_slots, status="scheduled"
        )
        db.add(new_session)
        await db.commit()

    return {"message": f"Session created for {s_date}: {s_start}-{s_end}, {total_slots} slots."}




@router.post("/cancel-appointment")                                                                                                                                       
async def cancel_appointment_api(request: ActionRequest, user: dict = Depends(get_current_user)):                                                                       
    async with async_session() as db:                                                                                                                                     
        result = await db.execute(
            select(Appointment, Patient)                                                                                                                                  
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(Patient.uhid == request.patient_uhid, Appointment.status.in_(["booked", "checked_in"]))
        )                                                                                                                                                                 
        row = result.first()
        if not row:                                                                                                                                                       
            raise HTTPException(status_code=404, detail="No active appointment found")
        appt, patient = row                                                                                                                                               
        appt.status = "cancelled"
        patient.risk_score += 10                                                                                                                                          
        await db.commit()
    return {"message": f"Appointment cancelled for {request.patient_uhid}. Risk score +10."}
