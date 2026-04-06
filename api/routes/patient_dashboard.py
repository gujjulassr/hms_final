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
from datetime import date, datetime

router = APIRouter()
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return decode_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    """Get logged-in patient's full profile."""
    async with async_session() as db:
        pat_result = await db.execute(
            select(Patient, User).join(User, Patient.user_id == User.id).where(User.email == user["email"])
        )
        pat_row = pat_result.first()
        if not pat_row:
            return {"error": "Patient not found"}
        patient, pat_user = pat_row

    return {
        "uhid": patient.uhid,
        "name": pat_user.full_name,
        "email": pat_user.email,
        "phone": pat_user.phone or "",
        "gender": patient.gender or "",
        "blood_group": patient.blood_group or "",
        "date_of_birth": str(patient.date_of_birth) if patient.date_of_birth else "",
        "address": patient.address or "",
        "emergency_contact_name": patient.emergency_contact_name or "",
        "emergency_contact_phone": patient.emergency_contact_phone or "",
        "risk_score": patient.risk_score
    }


class UpdateProfileRequest(BaseModel):
    full_name: str = ""
    phone: str = ""
    gender: str = ""
    blood_group: str = ""
    date_of_birth: str = ""
    address: str = ""
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""


@router.put("/profile")
async def update_profile(request: UpdateProfileRequest, user: dict = Depends(get_current_user)):
    """Update logged-in patient's profile."""
    async with async_session() as db:
        pat_result = await db.execute(
            select(Patient, User).join(User, Patient.user_id == User.id).where(User.email == user["email"])
        )
        pat_row = pat_result.first()
        if not pat_row:
            raise HTTPException(status_code=404, detail="Patient not found")
        patient, pat_user = pat_row

        if request.full_name:
            pat_user.full_name = request.full_name
        if request.phone:
            pat_user.phone = request.phone
        if request.gender:
            patient.gender = request.gender
        if request.blood_group:
            patient.blood_group = request.blood_group
        if request.date_of_birth:
            from datetime import datetime as dt
            try:
                patient.date_of_birth = dt.strptime(request.date_of_birth, "%Y-%m-%d").date()
            except ValueError:
                pass
        if request.address:
            patient.address = request.address
        if request.emergency_contact_name:
            patient.emergency_contact_name = request.emergency_contact_name
        if request.emergency_contact_phone:
            patient.emergency_contact_phone = request.emergency_contact_phone

        await db.commit()

    return {"message": "Profile updated successfully"}


@router.get("/status")
async def get_patient_status(user: dict = Depends(get_current_user)):
    """Get current appointment status, queue position, doctor status for logged-in patient."""
    async with async_session() as db:
        # Find patient
        pat_result = await db.execute(
            select(Patient, User).join(User, Patient.user_id == User.id).where(User.email == user["email"])
        )
        pat_row = pat_result.first()
        if not pat_row:
            return {"error": "Patient not found"}
        patient, pat_user = pat_row

        # Get today's appointments
        appt_result = await db.execute(
            select(Appointment, Session, Doctor, User)
            .join(Session, Appointment.session_id == Session.id)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(
                Appointment.patient_id == patient.id,
                Session.session_date == date.today(),
                Appointment.status.in_(["booked", "checked_in", "in_progress"])
            ).order_by(Appointment.slot_time)
        )
        all_appointments = appt_result.all()

        # Filter out past appointments (unless in_progress — doctor is currently seeing them)
        now = datetime.now().time()
        appointments = []
        for appt_row in all_appointments:
            appt = appt_row[0]
            if appt.status == "in_progress":
                appointments.append(appt_row)
            elif appt.slot_time >= now:
                appointments.append(appt_row)

        if not appointments:
            return {
                "uhid": patient.uhid,
                "name": pat_user.full_name,
                "has_appointment_today": False,
                "appointments": []
            }

        appt_list = []
        for appt, session, doctor, doc_user in appointments:
            # Count patients ahead in queue
            ahead_result = await db.execute(
                select(func.count(Appointment.id)).where(
                    Appointment.session_id == session.id,
                    Appointment.status.in_(["checked_in", "in_progress"]),
                    Appointment.slot_number < appt.slot_number,
                    Appointment.id != appt.id
                )
            )
            patients_ahead = ahead_result.scalar() or 0

            # Check if doctor is currently with someone
            busy_result = await db.execute(
                select(Appointment).where(
                    Appointment.session_id == session.id,
                    Appointment.status == "in_progress"
                )
            )
            doctor_busy = busy_result.scalars().first() is not None

            # Get slot position info
            same_slot_result = await db.execute(
                select(func.count(Appointment.id)).where(
                    Appointment.session_id == session.id,
                    Appointment.slot_number == appt.slot_number,
                    Appointment.status.in_(["booked", "checked_in", "in_progress"]),
                    Appointment.id != appt.id
                )
            )
            others_in_slot = same_slot_result.scalar() or 0

            appt_info = {
                "doctor": doc_user.full_name,
                "specialization": doctor.specialization,
                "date": str(session.session_date),
                "time": str(appt.slot_time),
                "slot_number": appt.slot_number,
                "slot_position": appt.slot_position,
                "status": appt.status,
                "checked_in": appt.status in ["checked_in", "in_progress"],
                "is_your_turn": appt.status == "in_progress",
                "doctor_busy": doctor_busy,
                "patients_ahead": patients_ahead,
                "others_in_slot": others_in_slot,
                "session_status": session.status,
                "message": ""
            }

            # Calculate estimated wait time
            estimated_wait = (patients_ahead * session.slot_duration_minutes) + session.delay_minutes
            appt_info["estimated_wait_minutes"] = estimated_wait

            # Generate status message
            if appt.status == "booked":
                appt_info["message"] = "Please visit the reception to check in."
            elif appt.status == "checked_in":
                if doctor_busy:
                    wait_msg = f"Estimated wait: ~{estimated_wait} minutes." if estimated_wait > 0 else ""
                    appt_info["message"] = f"Doctor is with another patient. {patients_ahead} patient(s) ahead of you. {wait_msg}"
                else:
                    appt_info["message"] = "Doctor is available. You will be called soon."
            elif appt.status == "in_progress":
                appt_info["message"] = "It's your turn! Please proceed to the doctor's room."

            appt_list.append(appt_info)

    return {
        "uhid": patient.uhid,
        "name": pat_user.full_name,
        "has_appointment_today": True,
        "appointments": appt_list
    }


@router.get("/doctors")
async def get_available_doctors(user: dict = Depends(get_current_user)):
    """Get all doctors with their availability for today."""
    async with async_session() as db:
        # Get all doctors
        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id)
        )
        doctors = doc_result.all()

        doctor_list = []
        for doctor, doc_user in doctors:
            # Get today's sessions
            session_result = await db.execute(
                select(Session).where(
                    Session.doctor_id == doctor.id,
                    Session.session_date == date.today(),
                    Session.status.in_(["scheduled", "active"])
                ).order_by(Session.start_time)
            )
            sessions = session_result.scalars().all()

            session_list = []
            for sess in sessions:
                # Count booked slots
                booked_result = await db.execute(
                    select(func.count(Appointment.id)).where(
                        Appointment.session_id == sess.id,
                        Appointment.status != "cancelled"
                    )
                )
                booked_count = booked_result.scalar() or 0
                total_capacity = sess.total_slots * sess.max_per_slot

                session_list.append({
                    "start_time": str(sess.start_time),
                    "end_time": str(sess.end_time),
                    "status": sess.status,
                    "total_slots": sess.total_slots,
                    "booked": booked_count,
                    "capacity": total_capacity,
                    "available": total_capacity - booked_count
                })

            doctor_list.append({
                "name": doc_user.full_name,
                "specialization": doctor.specialization,
                "fee": doctor.consultation_fee,
                "rating": doctor.avg_rating,
                "total_ratings": doctor.total_ratings,
                "sessions_today": session_list
            })

    return {"doctors": doctor_list}


@router.get("/appointments")
async def get_all_appointments(user: dict = Depends(get_current_user)):
    """Get all appointments (past, present, future) for the logged-in patient."""
    async with async_session() as db:
        pat_result = await db.execute(
            select(Patient, User).join(User, Patient.user_id == User.id).where(User.email == user["email"])
        )
        pat_row = pat_result.first()
        if not pat_row:
            return {"appointments": []}
        patient, pat_user = pat_row

        appt_result = await db.execute(
            select(Appointment, Session, Doctor, User)
            .join(Session, Appointment.session_id == Session.id)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(Appointment.patient_id == patient.id)
            .order_by(Session.session_date.desc(), Appointment.slot_time.desc())
        )
        rows = appt_result.all()

    appt_list = []
    for appt, session, doctor, doc_user in rows:
        appt_list.append({
            "doctor": doc_user.full_name,
            "specialization": doctor.specialization,
            "date": str(session.session_date),
            "time": str(appt.slot_time),
            "slot": appt.slot_number,
            "status": appt.status,
            "notes": appt.notes or "",
            "is_emergency": appt.is_emergency
        })

    return {"uhid": patient.uhid, "name": pat_user.full_name, "appointments": appt_list}


@router.get("/beneficiaries")
async def get_beneficiaries(user: dict = Depends(get_current_user)):
    """Get all beneficiaries for the logged-in patient."""
    from models.beneficiary import Beneficiary
    async with async_session() as db:
        pat_result = await db.execute(
            select(Patient, User).join(User, Patient.user_id == User.id).where(User.email == user["email"])
        )
        pat_row = pat_result.first()
        if not pat_row:
            return {"beneficiaries": []}
        patient, pat_user = pat_row

        result = await db.execute(
            select(Beneficiary, Patient, User)
            .join(Patient, Beneficiary.beneficiary_patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .where(Beneficiary.patient_id == patient.id)
        )
        rows = result.all()

    ben_list = []
    for ben, ben_patient, ben_user in rows:
        ben_list.append({
            "uhid": ben_patient.uhid,
            "name": ben_user.full_name,
            "relationship": ben.relationship,
            "phone": ben_user.phone or "",
            "gender": ben_patient.gender or "",
            "blood_group": ben_patient.blood_group or "",
            "address": ben_patient.address or "",
            "emergency_contact_name": ben_patient.emergency_contact_name or "",
            "emergency_contact_phone": ben_patient.emergency_contact_phone or "",
            "date_of_birth": str(ben_patient.date_of_birth) if ben_patient.date_of_birth else ""
        })

    return {"patient_uhid": patient.uhid, "beneficiaries": ben_list}


class AddBeneficiaryRequest(BaseModel):
    full_name: str
    email: str
    phone: str
    gender: str
    blood_group: str
    relationship: str


@router.post("/beneficiaries")
async def add_beneficiary_api(request: AddBeneficiaryRequest, user: dict = Depends(get_current_user)):
    """Register a new family member and link as beneficiary."""
    from models.beneficiary import Beneficiary
    from services.auth import hash_password
    import uuid as uuid_lib
    from datetime import datetime as dt

    async with async_session() as db:
        # Find logged-in patient
        pat_result = await db.execute(
            select(Patient, User).join(User, Patient.user_id == User.id).where(User.email == user["email"])
        )
        pat_row = pat_result.first()
        if not pat_row:
            raise HTTPException(status_code=404, detail="Patient not found")
        patient, pat_user = pat_row

        # Check if email already exists
        existing = await db.execute(select(User).where(User.email == request.email))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Email already registered")

        # Generate UHID
        uhid_result = await db.execute(select(Patient).order_by(Patient.uhid.desc()))
        last_patient = uhid_result.scalars().first()
        if last_patient:
            last_number = int(last_patient.uhid.split("-")[-1])
            new_uhid = f"HMS-{dt.now().year}-{str(last_number + 1).zfill(5)}"
        else:
            new_uhid = f"HMS-{dt.now().year}-00001"

        # Create user
        new_user = User(
            id=uuid_lib.uuid4(),
            email=request.email,
            phone=request.phone,
            password_hash=hash_password("password123"),
            full_name=request.full_name,
            role="patient",
            is_active=True
        )
        db.add(new_user)
        await db.flush()

        # Create patient
        new_patient = Patient(
            id=uuid_lib.uuid4(),
            user_id=new_user.id,
            uhid=new_uhid,
            gender=request.gender,
            blood_group=request.blood_group
        )
        db.add(new_patient)
        await db.flush()

        # Link as beneficiary
        new_ben = Beneficiary(
            id=uuid_lib.uuid4(),
            patient_id=patient.id,
            beneficiary_patient_id=new_patient.id,
            relationship=request.relationship.lower()
        )
        db.add(new_ben)
        await db.commit()

    return {"message": f"Family member registered! UHID: {new_uhid}", "uhid": new_uhid, "name": request.full_name}


class UpdateBeneficiaryRequest(BaseModel):
    uhid: str
    full_name: str = ""
    phone: str = ""
    gender: str = ""
    blood_group: str = ""
    date_of_birth: str = ""
    address: str = ""
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""


@router.put("/beneficiaries")
async def update_beneficiary(request: UpdateBeneficiaryRequest, user: dict = Depends(get_current_user)):
    """Update a beneficiary's details."""
    from models.beneficiary import Beneficiary

    async with async_session() as db:
        # Verify logged-in patient owns this beneficiary
        pat_result = await db.execute(
            select(Patient).join(User, Patient.user_id == User.id).where(User.email == user["email"])
        )
        patient = pat_result.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Find beneficiary
        ben_result = await db.execute(
            select(Patient, User)
            .join(User, Patient.user_id == User.id)
            .where(Patient.uhid == request.uhid)
        )
        ben_row = ben_result.first()
        if not ben_row:
            raise HTTPException(status_code=404, detail="Beneficiary not found")

        ben_patient, ben_user = ben_row

        # Verify it's actually a beneficiary of this patient
        link = await db.execute(
            select(Beneficiary).where(
                Beneficiary.patient_id == patient.id,
                Beneficiary.beneficiary_patient_id == ben_patient.id
            )
        )
        if not link.scalars().first():
            raise HTTPException(status_code=403, detail="Not your beneficiary")

        # Update fields
        if request.full_name:
            ben_user.full_name = request.full_name
        if request.phone:
            ben_user.phone = request.phone
        if request.gender:
            ben_patient.gender = request.gender
        if request.blood_group:
            ben_patient.blood_group = request.blood_group
        if request.date_of_birth:
            from datetime import datetime as dt
            try:
                ben_patient.date_of_birth = dt.strptime(request.date_of_birth, "%Y-%m-%d").date()
            except ValueError:
                pass
        if request.address:
            ben_patient.address = request.address
        if request.emergency_contact_name:
            ben_patient.emergency_contact_name = request.emergency_contact_name
        if request.emergency_contact_phone:
            ben_patient.emergency_contact_phone = request.emergency_contact_phone

        await db.commit()

    return {"message": f"Beneficiary {request.uhid} updated successfully"}
