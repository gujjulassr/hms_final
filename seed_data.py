import asyncio
import uuid
from datetime import datetime, date, time
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config.settings import DATABASE_URL
from models.user import User
from models.doctor import Doctor
from models.patient import Patient
from models.session import Session
from models.appointment import Appointment


async def seed():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Step 1: Users first
        admin = User(
            id=uuid.uuid4(),
            email="admin@hosp.com",
            phone="9999999999",
            password_hash="hashed_admin123",
            full_name="Admin User",
            role="admin",
            is_active=True
        )
        doc_user1 = User(
            id=uuid.uuid4(),
            email="shah@hosp.com",
            phone="9999999901",
            password_hash="hashed_doc123",
            full_name="Dr. Shah",
            role="doctor",
            is_active=True
        )
        doc_user2 = User(
            id=uuid.uuid4(),
            email="priya@hosp.com",
            phone="9999999902",
            password_hash="hashed_doc123",
            full_name="Dr. Priya",
            role="doctor",
            is_active=True
        )
        pat_user1 = User(
            id=uuid.uuid4(),
            email="arjun@gmail.com",
            phone="8888888801",
            password_hash="hashed_pat123",
            full_name="Arjun Kumar",
            role="patient",
            is_active=True
        )
        pat_user2 = User(
            id=uuid.uuid4(),
            email="meera@gmail.com",
            phone="8888888802",
            password_hash="hashed_pat123",
            full_name="Meera Sharma",
            role="patient",
            is_active=True
        )
        pat_user3 = User(
            id=uuid.uuid4(),
            email="ravi@gmail.com",
            phone="8888888803",
            password_hash="hashed_pat123",
            full_name="Ravi Patel",
            role="patient",
            is_active=True
        )
        db.add_all([admin, doc_user1, doc_user2, pat_user1, pat_user2, pat_user3])
        await db.flush()

        # Step 2: Doctors and Patients (depend on users)
        doctor1 = Doctor(
            id=uuid.uuid4(),
            user_id=doc_user1.id,
            specialization="Cardiology",
            qualification="MD Cardiology",
            consultation_fee=500
        )
        doctor2 = Doctor(
            id=uuid.uuid4(),
            user_id=doc_user2.id,
            specialization="Pediatrics",
            qualification="MD Pediatrics",
            consultation_fee=400
        )
        patient1 = Patient(
            id=uuid.uuid4(),
            user_id=pat_user1.id,
            uhid="HMS-2026-00001",
            blood_group="O+",
            gender="Male",
            date_of_birth=date(1990, 5, 15),
            address="Mumbai",
            emergency_contact_name="Priya Kumar",
            emergency_contact_phone="8888888810"
        )
        patient2 = Patient(
            id=uuid.uuid4(),
            user_id=pat_user2.id,
            uhid="HMS-2026-00002",
            blood_group="A+",
            gender="Female",
            date_of_birth=date(1985, 8, 20),
            address="Delhi"
        )
        patient3 = Patient(
            id=uuid.uuid4(),
            user_id=pat_user3.id,
            uhid="HMS-2026-00003",
            blood_group="B+",
            gender="Male",
            date_of_birth=date(2024, 1, 10),
            address="Pune"
        )
        db.add_all([doctor1, doctor2, patient1, patient2, patient3])
        await db.flush()

        # Step 3: Sessions (depend on doctors)
        session1 = Session(
            id=uuid.uuid4(),
            doctor_id=doctor1.id,
            session_date=date.today(),
            start_time=time(9, 0),
            end_time=time(13, 0),
            slot_duration_minutes=15,
            max_per_slot=2,
            total_slots=16,
            status="scheduled"
        )
        session2 = Session(
            id=uuid.uuid4(),
            doctor_id=doctor2.id,
            session_date=date.today(),
            start_time=time(14, 0),
            end_time=time(18, 0),
            slot_duration_minutes=15,
            max_per_slot=2,
            total_slots=16,
            status="scheduled"
        )
        db.add_all([session1, session2])
        await db.flush()

        # Step 4: Appointments (depend on sessions and patients)
        appt1 = Appointment(
            id=uuid.uuid4(),
            session_id=session1.id,
            patient_id=patient1.id,
            booked_by=pat_user1.id,
            slot_number=1,
            slot_position=1,
            slot_time=time(9, 0),
            status="booked"
        )
        appt2 = Appointment(
            id=uuid.uuid4(),
            session_id=session1.id,
            patient_id=patient2.id,
            booked_by=pat_user2.id,
            slot_number=2,
            slot_position=1,
            slot_time=time(9, 15),
            status="booked"
        )
        db.add_all([appt1, appt2])

        await db.commit()
        print("Seed data inserted successfully!")

    await engine.dispose()


asyncio.run(seed())
