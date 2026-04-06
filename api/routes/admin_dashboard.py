from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select, func
from models.appointment import Appointment
from models.patient import Patient
from models.session import Session
from models.doctor import Doctor
from models.user import User
from models.audit_log import AuditLog
from config.database import AsyncSessionLocal as async_session
from services.auth import decode_token, hash_password
from datetime import date, datetime, timedelta
import uuid as uuid_lib

router = APIRouter()
security = HTTPBearer()


async def get_admin_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = decode_token(credentials.credentials)
        if payload["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin access only")
        return payload
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ==========================================
# USER MANAGEMENT
# ==========================================

@router.get("/users")
async def list_users(role: str = "", user: dict = Depends(get_admin_user)):
    """List all users, optionally filter by role."""
    async with async_session() as db:
        query = select(User).order_by(User.full_name)
        if role:
            query = query.where(User.role == role)
        result = await db.execute(query)
        users = result.scalars().all()

        user_list = []
        for u in users:
            info = {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "phone": u.phone or "",
                "role": u.role,
                "is_active": u.is_active,
                "specialization": "",
                "qualification": "",
                "consultation_fee": 0,
                "avg_rating": 0.0,
                "uhid": "",
                "gender": "",
                "blood_group": "",
                "date_of_birth": "",
                "address": "",
                "risk_score": 0
            }

            if u.role == "doctor":
                doc_result = await db.execute(select(Doctor).where(Doctor.user_id == u.id))
                doc = doc_result.scalars().first()
                if doc:
                    info["specialization"] = doc.specialization or ""
                    info["qualification"] = doc.qualification or ""
                    info["consultation_fee"] = doc.consultation_fee
                    info["avg_rating"] = doc.avg_rating

            if u.role == "patient":
                pat_result = await db.execute(select(Patient).where(Patient.user_id == u.id))
                pat = pat_result.scalars().first()
                if pat:
                    info["uhid"] = pat.uhid or ""
                    info["gender"] = pat.gender or ""
                    info["blood_group"] = pat.blood_group or ""
                    info["date_of_birth"] = str(pat.date_of_birth) if pat.date_of_birth else ""
                    info["address"] = pat.address or ""
                    info["risk_score"] = pat.risk_score

            user_list.append(info)

    return {"users": user_list}


class CreateUserRequest(BaseModel):
    full_name: str
    email: str
    phone: str
    password: str
    role: str
    specialization: str = ""
    qualification: str = ""
    consultation_fee: int = 0


@router.post("/users")
async def create_user(request: CreateUserRequest, user: dict = Depends(get_admin_user)):
    """Create a new user (doctor, nurse, admin, patient)."""
    if request.role not in ["doctor", "nurse", "admin", "patient"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    async with async_session() as db:
        existing = await db.execute(select(User).where(User.email == request.email))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Email already exists")

        new_user = User(
            id=uuid_lib.uuid4(),
            email=request.email,
            phone=request.phone,
            password_hash=hash_password(request.password),
            full_name=request.full_name,
            role=request.role,
            is_active=True
        )
        db.add(new_user)
        await db.flush()

        # If doctor, create doctor profile
        if request.role == "doctor":
            doctor = Doctor(
                id=uuid_lib.uuid4(),
                user_id=new_user.id,
                specialization=request.specialization,
                qualification=request.qualification,
                consultation_fee=request.consultation_fee
            )
            db.add(doctor)

        # If patient, create patient profile with UHID
        if request.role == "patient":
            pat_result = await db.execute(select(Patient).order_by(Patient.uhid.desc()))
            last = pat_result.scalars().first()
            if last:
                num = int(last.uhid.split("-")[-1]) + 1
            else:
                num = 1
            uhid = f"HMS-{datetime.now().year}-{str(num).zfill(5)}"

            patient = Patient(
                id=uuid_lib.uuid4(),
                user_id=new_user.id,
                uhid=uhid
            )
            db.add(patient)

        await db.commit()

    return {"message": f"{request.role.title()} '{request.full_name}' created successfully."}


class ToggleUserRequest(BaseModel):
    user_id: str


class UpdateUserRequest(BaseModel):
    user_id: str
    full_name: str = ""
    phone: str = ""
    email: str = ""
    specialization: str = ""
    qualification: str = ""
    consultation_fee: int = -1


@router.put("/users")
async def update_user(request: UpdateUserRequest, user: dict = Depends(get_admin_user)):
    """Update a user's details. For doctors, can also update specialization, qualification, fee."""
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == uuid_lib.UUID(request.user_id)))
        target = result.scalars().first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        if request.full_name:
            target.full_name = request.full_name
        if request.phone:
            target.phone = request.phone
        if request.email:
            target.email = request.email

        # If doctor, update doctor profile too
        if target.role == "doctor":
            doc_result = await db.execute(select(Doctor).where(Doctor.user_id == target.id))
            doctor = doc_result.scalars().first()
            if doctor:
                if request.specialization:
                    doctor.specialization = request.specialization
                if request.qualification:
                    doctor.qualification = request.qualification
                if request.consultation_fee >= 0:
                    doctor.consultation_fee = request.consultation_fee

        await db.commit()

    return {"message": f"{target.full_name} updated successfully."}


@router.post("/users/toggle")
async def toggle_user(request: ToggleUserRequest, user: dict = Depends(get_admin_user)):
    """Activate or deactivate a user."""
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == uuid_lib.UUID(request.user_id)))
        target = result.scalars().first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        target.is_active = not target.is_active
        await db.commit()

    status = "activated" if target.is_active else "deactivated"
    return {"message": f"{target.full_name} {status}."}


# ==========================================
# SESSION MANAGEMENT
# ==========================================

@router.get("/sessions")
async def list_sessions(session_date: str = "", department: str = "", doctor_name: str = "", user: dict = Depends(get_admin_user)):
    """List sessions with filters: date, department (specialization), doctor name."""
    async with async_session() as db:
        query = (
            select(Session, Doctor, User)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
        )

        if session_date:
            try:
                d = datetime.strptime(session_date, "%Y-%m-%d").date()
                query = query.where(Session.session_date == d)
            except ValueError:
                pass
        else:
            query = query.where(Session.session_date >= date.today())

        if department:
            query = query.where(Doctor.specialization.ilike(f"%{department}%"))

        if doctor_name:
            query = query.where(User.full_name.ilike(f"%{doctor_name}%"))

        query = query.where(Session.status != "cancelled")
        query = query.order_by(Session.session_date, Session.start_time)

        result = await db.execute(query)
        rows = result.all()

    session_list = []
    for sess, doctor, doc_user in rows:
        session_list.append({
            "id": str(sess.id),
            "date": str(sess.session_date),
            "start_time": str(sess.start_time),
            # "end_time": str(sess.end_time),
            "end_time": str((datetime.combine(sess.session_date, sess.end_time) + timedelta(minutes=sess.overtime_minutes)).time()) if sess.overtime_minutes > 0 else str(sess.end_time), 
            "status": sess.status,
            "total_slots": sess.total_slots,
            "doctor": doc_user.full_name,
            "department": doctor.specialization,
            "overtime": sess.overtime_minutes,
            "delay": sess.delay_minutes,
            "original_end_time":str(sess.end_time),
        })

    return {"sessions": session_list}


class SessionActionRequest(BaseModel):
    session_id: str


# @router.post("/revert-session")
# async def revert_session(request: SessionActionRequest, user: dict = Depends(get_admin_user)):
#     """Revert an active session back to scheduled status."""
#     async with async_session() as db:
#         sess_result = await db.execute(
#             select(Session).where(Session.id == uuid_lib.UUID(request.session_id))
#         )
#         session = sess_result.scalars().first()
#         if not session:
#             raise HTTPException(status_code=404, detail="Session not found")
#         if session.status != "active":
#             raise HTTPException(status_code=400, detail=f"Can only revert active sessions. Current: {session.status}")

#         session.status = "scheduled"
#         await db.commit()

#     return {"message": "Session reverted to scheduled."}


# ==========================================
# STATS
# ==========================================

@router.get("/stats")
async def get_stats(user: dict = Depends(get_admin_user)):
    """Get system-wide statistics."""
    async with async_session() as db:
        total_users = (await db.execute(select(func.count(User.id)))).scalar()
        total_patients = (await db.execute(select(func.count(Patient.id)))).scalar()
        total_doctors = (await db.execute(select(func.count(Doctor.id)))).scalar()
        total_nurses = (await db.execute(select(func.count(User.id)).where(User.role == "nurse"))).scalar()

        today_appts = (await db.execute(
            select(func.count(Appointment.id))
            .join(Session, Appointment.session_id == Session.id)
            .where(Session.session_date == date.today())
        )).scalar()

        today_completed = (await db.execute(
            select(func.count(Appointment.id))
            .join(Session, Appointment.session_id == Session.id)
            .where(Session.session_date == date.today(), Appointment.status == "completed")
        )).scalar()

        today_no_show = (await db.execute(
            select(func.count(Appointment.id))
            .join(Session, Appointment.session_id == Session.id)
            .where(Session.session_date == date.today(), Appointment.status == "no_show")
        )).scalar()

    return {
        "total_users": total_users,
        "total_patients": total_patients,
        "total_doctors": total_doctors,
        "total_nurses": total_nurses,
        "today_appointments": today_appts,
        "today_completed": today_completed,
        "today_no_show": today_no_show
    }


# ==========================================
# AUDIT LOG
# ==========================================

@router.get("/audit")
async def get_audit(limit: int = 50, user: dict = Depends(get_admin_user)):
    """Get recent audit log entries."""
    async with async_session() as db:
        result = await db.execute(
            select(AuditLog, User)
            .join(User, AuditLog.user_id == User.id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        rows = result.all()

    return {"logs": [{
        "timestamp": log.created_at.strftime("%Y-%m-%d %H:%M"),
        "user": u.full_name,
        "action": log.action,
        "target_type": log.target_type,
        "details": log.details or {}
    } for log, u in rows]}


# ==========================================
# DEPARTMENTS
# ==========================================

@router.get("/appointments")
async def list_appointments(session_date: str = "", department: str = "", doctor_name: str = "", status: str = "", user: dict = Depends(get_admin_user)):
    """List all appointments with filters."""
    async with async_session() as db:
        query = (
            select(Appointment, Patient, User, Session, Doctor)
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .join(Session, Appointment.session_id == Session.id)
            .join(Doctor, Session.doctor_id == Doctor.id)
        )

        # Need doctor user for name
        from sqlalchemy.orm import aliased
        DoctorUser = aliased(User)
        query = (
            select(Appointment, Patient, User, Session, Doctor, DoctorUser)
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .join(Session, Appointment.session_id == Session.id)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(DoctorUser, Doctor.user_id == DoctorUser.id)
        )

        if session_date:
            try:
                d = datetime.strptime(session_date, "%Y-%m-%d").date()
                query = query.where(Session.session_date == d)
            except ValueError:
                pass
        else:
            query = query.where(Session.session_date >= date.today())

        if department:
            query = query.where(Doctor.specialization.ilike(f"%{department}%"))

        if doctor_name:
            query = query.where(DoctorUser.full_name.ilike(f"%{doctor_name}%"))

        if status:
            query = query.where(Appointment.status == status)

        query = query.order_by(Session.session_date, Appointment.slot_time)
        result = await db.execute(query)
        rows = result.all()

    appt_list = []
    for appt, patient, pat_user, session, doctor, doc_user in rows:
        appt_list.append({
            "uhid": patient.uhid,
            "patient_name": pat_user.full_name,
            "doctor": doc_user.full_name,
            "department": doctor.specialization,
            "date": str(session.session_date),
            "time": str(appt.slot_time),
            "slot": appt.slot_number,
            "status": appt.status,
            "priority": appt.priority,
            "is_emergency": appt.is_emergency
        })

    return {"appointments": appt_list}


@router.get("/departments")
async def list_departments(user: dict = Depends(get_admin_user)):
    """List all departments (specializations) with doctor count."""
    async with async_session() as db:
        result = await db.execute(
            select(Doctor.specialization, func.count(Doctor.id).label("count"))
            .group_by(Doctor.specialization)
        )
        rows = result.all()

    return {"departments": [{"name": r[0], "doctors": r[1]} for r in rows]}
