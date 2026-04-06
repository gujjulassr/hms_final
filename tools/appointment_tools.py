from langchain_core.tools import tool
from sqlalchemy import select, func
from models.session import Session
from models.appointment import Appointment
from models.patient import Patient
from models.doctor import Doctor
from models.user import User
from config.database import AsyncSessionLocal as async_session
import uuid
from datetime import datetime, timedelta, date
from services.audit import log_action
from services.notifications.service import notify_booking, notify_cancellation


async def find_free_slot(db, session, preferred_time=""):
    """Find first available slot in a session. Returns (slot_number, position, slot_time) or None."""
    start = datetime.combine(session.session_date, session.start_time)

    # Get occupied slots
    slot_counts = await db.execute(
        select(Appointment.slot_number, func.count(Appointment.id).label("count")).where(
            Appointment.session_id == session.id,
            Appointment.status.in_(["booked", "checked_in", "in_progress"])
        ).group_by(Appointment.slot_number)
    )
    occupied = {row.slot_number: row.count for row in slot_counts}

    # Calculate minimum slot (skip past times if today)
    min_slot = 1
    if session.session_date == date.today():
        diff = (datetime.now() - start).total_seconds() / 60
        min_slot = int(diff // session.slot_duration_minutes) + 2

    print(f"[DEBUG find_free_slot] session: {session.start_time}-{session.end_time}, total_slots: {session.total_slots}, min_slot: {min_slot}")

    # If preferred time, calculate target slot
    target_slot = min_slot
    if preferred_time:
        print(f"[DEBUG find_free_slot] preferred_time: {preferred_time}, target_slot: {target_slot}, searching range: {target_slot} to {session.total_slots}")
        pref = datetime.strptime(preferred_time, "%H:%M").time()
        pref_diff = (datetime.combine(session.session_date, pref) - start).total_seconds() / 60
        target_slot = max(int(pref_diff // session.slot_duration_minutes) + 1, min_slot)

    # Search for free slot
    for slot_num in range(target_slot, session.total_slots + 1):
        count = occupied.get(slot_num, 0)
        if count < session.max_per_slot:
            slot_time = (start + timedelta(minutes=(slot_num - 1) * session.slot_duration_minutes)).time()
            return slot_num, count + 1, slot_time

    return None


@tool
async def book_appointment(patient_uhid: str, doctor_name: str, preferred_time: str = "") -> str:
    """Book an appointment for a patient with a doctor. Provide patient UHID, doctor name, and optionally preferred time like '09:15'."""
    async with async_session() as db:
        # Step 1: Check if preferred time is in past
        if preferred_time:
            try:
                pref = datetime.strptime(preferred_time, "%H:%M").time()
                if pref < datetime.now().time():
                    return f"{preferred_time} has already passed. Choose a future time."
            except ValueError:
                return "Invalid time format. Use HH:MM like '09:15'."

        # Step 2: Find patient
        patient_result = await db.execute(select(Patient).where(Patient.uhid == patient_uhid))
        patient = patient_result.scalars().first()
        if not patient:
            return f"Patient {patient_uhid} not found."

        # Step 3: Find doctor
        doctor_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.full_name.ilike(f"%{doctor_name}%"))
        )
        doctor_row = doctor_result.first()
        if not doctor_row:
            return f"Doctor {doctor_name} not found."
        doctor, doc_user = doctor_row

        # Step 4: Find all available sessions
        session_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.status.in_(["scheduled", "active"]),
                Session.session_date >= date.today()
            ).order_by(Session.session_date, Session.start_time)
        )
        all_sessions = session_result.scalars().all()
        if not all_sessions:
            return f"No available sessions for Dr. {doc_user.full_name}."

        # Step 5: Try each session until we find a free slot
        found_slot = None
        found_position = None
        slot_time = None
        chosen_session = None

        for s in all_sessions:
            print(f"[DEBUG booking] Checking session: {s.session_date} {s.start_time}-{s.end_time} status:{s.status}")
            actual_end = (datetime.combine(s.session_date, s.end_time) + timedelta(minutes=s.overtime_minutes)).time() if s.overtime_minutes > 0 else s.end_time
            if s.session_date == date.today() and actual_end <= datetime.now().time(): 
                print(f"[DEBUG booking] Skipping — end_time {s.end_time} <= now {datetime.now().time()}")
                continue

            result = await find_free_slot(db, s, preferred_time)
            print(f"[DEBUG booking] find_free_slot result: {result}")
            if result:
                found_slot, found_position, slot_time = result
                chosen_session = s
                break

        if not found_slot:
            return f"No available slots for Dr. {doc_user.full_name} in any session."

        # Step 6: Create appointment
        new_appt = Appointment(
            id=uuid.uuid4(),
            session_id=chosen_session.id,
            patient_id=patient.id,
            booked_by=patient.user_id,
            slot_number=found_slot,
            slot_position=found_position,
            slot_time=slot_time,
            status="booked"
        )
        db.add(new_appt)
        await log_action(db, patient.user_id, "BOOK", "appointment", new_appt.id, {"uhid": patient_uhid, "doctor": doc_user.full_name, "slot": found_slot, "time": str(slot_time)})
        await db.commit()

    return f"Appointment booked! Patient: {patient_uhid}, Doctor: {doc_user.full_name}, Date: {chosen_session.session_date}, Time: {slot_time}, Slot: {found_slot}"





@tool                                                                                                                                                                     
async def check_earliest_slot(doctor_name: str) -> str:
    """Check the earliest available slot for a doctor without booking."""
    async with async_session() as db:
        doctor_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.full_name.ilike(f"%{doctor_name}%"))                                                    
        )
        doctor_row = doctor_result.first()                                                                                                                                
        if not doctor_row:                                                                                                                                                
            return f"Doctor {doctor_name} not found."
        doctor, doc_user = doctor_row                                                                                                                                     
                
        session_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,                                                                                                                           
                Session.status.in_(["scheduled", "active"]),
                Session.session_date >= date.today()                                                                                                                      
            ).order_by(Session.session_date, Session.start_time)
        )
        all_sessions = session_result.scalars().all()
        if not all_sessions:                                                                                                                                              
            return f"No available sessions for Dr. {doc_user.full_name}."
                                                                                                                                                                        
        for s in all_sessions:
            if s.session_date == date.today() and s.end_time <= datetime.now().time():
                continue                                                                                                                                                  
            result = await find_free_slot(db, s)
            if result:                                                                                                                                                    
                slot_num, position, slot_time = result
                return f"Earliest slot for Dr. {doc_user.full_name}: {s.session_date} at {slot_time} (Slot {slot_num}). Say 'book' to confirm."                           
                                                                                                                                                                        
    return f"No available slots for Dr. {doc_user.full_name}."  



@tool                                                                                                                                                                     
async def get_my_appointments(patient_uhid: str) -> str:                                                                                                                
    """Get all appointments for a patient by their UHID."""                                                                                                               
    async with async_session() as db:
        result = await db.execute(                                                                                                                                        
            select(Appointment, Session, Doctor, User)                                                                                                                  
            .join(Session, Appointment.session_id == Session.id)                                                                                                          
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)                                                                                                                        
            .where(                                                                                                                                                     
                Appointment.patient_id.in_(                                                                                                                               
                    select(Patient.id).where(Patient.uhid == patient_uhid)                                                                                              
                )                                                                                                                                                         
            ).order_by(Session.session_date.desc(), Appointment.slot_time.desc())
        )                                                                                                                                                                 
        rows = result.all()                                                                                                                                             
                                                                                                                                                                        
    if not rows:                                                                                                                                                        
        return "No appointments found."
                                                                                                                                                                        
    output = ""
    for appt, session, doctor, user in rows:                                                                                                                              
        output += f"Doctor: {user.full_name}, Date: {session.session_date}, Time: {appt.slot_time}, Status: {appt.status}, Slot: {appt.slot_number}\n"                  
    return output   


@tool                                                                                                                                                                     
async def cancel_appointment(patient_uhid: str, doctor_name: str) -> str:
    """Cancel a patient's booked appointment with a doctor."""                                                                                                            
    async with async_session() as db:                                                                                                                                   
        result = await db.execute(
            select(Appointment, Patient, Session, Doctor, User)                                                                                                           
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(Session, Appointment.session_id == Session.id)                                                                                                          
            .join(Doctor, Session.doctor_id == Doctor.id)                                                                                                               
            .join(User, Doctor.user_id == User.id)                                                                                                                        
            .where(                                                                                                                                                     
                Patient.uhid == patient_uhid,
                User.full_name.ilike(f"%{doctor_name}%"),                                                                                                                 
                Appointment.status.in_(["booked","checked_in"]),
                Session.session_date >= date.today()                                                                                                                      
            ).order_by(Session.session_date, Appointment.slot_time)                                                                                                       
        )
        rows = result.all()                                                                                                                                               
                                                                                                                                                                        
        if not rows:
            return "No booked appointment found to cancel."                                                                                                               
                                                                                                                                                                        
        # Find first future appointment                                                                                                                                   
        appt, patient, session, doctor, doc_user = None, None, None, None, None
        for row in rows:                                                                                                                                                  
            row_appt, row_patient, row_session, row_doctor, row_doc_user = row                                                                                          
            if row_session.session_date > date.today():                                                                                                                   
                appt, patient, session, doctor, doc_user = row_appt, row_patient, row_session, row_doctor, row_doc_user
                break                                                                                                                                                     
            if row_session.session_date == date.today() and row_appt.slot_time >= datetime.now().time():                                                                
                appt, patient, session, doctor, doc_user = row_appt, row_patient, row_session, row_doctor, row_doc_user                                                   
                break                                                                                                                                                   
                                                                                                                                                                        
        if not appt:                                                                                                                                                      
            return "All booked appointments have already passed."
                                                                                                                                                                        
        appt.status = "cancelled"                                                                                                                                       
        patient.risk_score += 10
        await log_action(db, patient.user_id, "CANCEL", "appointment", appt.id, {"uhid": patient_uhid, "doctor": doc_user.full_name})                                     
        await db.commit()                                                                                                                                                 
                                                                                                                                                                        
    return f"Appointment cancelled for {patient_uhid} with Dr. {doc_user.full_name} on {session.session_date} at {appt.slot_time}. Risk score +10."  
