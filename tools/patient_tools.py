from langchain_core.tools import tool
from sqlalchemy import select
from models.patient import Patient
from models.user import User
from config.database import AsyncSessionLocal as async_session
import uuid
from datetime import datetime
from services.audit import log_action


@tool
async def search_patients(query: str) -> str:
    """Search patients by name or UHID."""
    async with async_session() as db:
        stmt = select(Patient, User).join(User, Patient.user_id == User.id).where(
            (User.full_name.ilike(f"%{query}%")) | (Patient.uhid.ilike(f"%{query}%"))
        )
        result = await db.execute(stmt)
        rows = result.all()

    if not rows:
        return "No patients found."

    output = ""
    for patient, user in rows:
        output += f"UHID: {patient.uhid}, Name: {user.full_name}, Blood Group: {patient.blood_group}, Gender: {patient.gender}\n"
    return output



@tool
async def get_patient_details(query:str)->str:
    """Get full details of a patient by name or UHID."""

    async with async_session() as db:
        stmt=select(Patient,User).join(User,Patient.user_id==User.id).where(
            (User.full_name.ilike(f"%{query}%")) |

            (Patient.uhid==query)
        )
        result=await db.execute(stmt)
        row=result.first()


    if not row:
        return "Patient not found"

    patient,user=row
    return (                                                                                                                   
          f"UHID: {patient.uhid}\n"
          f"Name: {user.full_name}\n"
          f"Email: {user.email}\n"
          f"Phone: {user.phone}\n"                                                                                               
          f"Blood Group: {patient.blood_group}\n"
          f"Gender: {patient.gender}\n"                                                                                          
          f"DOB: {patient.date_of_birth}\n"
          f"Address: {patient.address}\n"                                                                                        
          f"Emergency Contact: {patient.emergency_contact_name} ({patient.emergency_contact_phone})\n"
          f"Risk Score: {patient.risk_score}\n"                                                                                  
      )



@tool
async def register_patient(
    full_name: str,
    email: str,
    phone: str,
    gender: str,
    blood_group: str
) -> str:
    """Register a new patient in the system. Returns their UHID."""
    async with async_session() as db:
        # Generate UHID
        result = await db.execute(select(Patient).order_by(Patient.uhid.desc()))
        last_patient = result.scalars().first()

        if last_patient:
            last_number = int(last_patient.uhid.split("-")[-1])
            new_uhid = f"HMS-{datetime.now().year}-{str(last_number + 1).zfill(5)}"
        else:
            new_uhid = f"HMS-{datetime.now().year}-00001"

        # Create user
        new_user = User(
            id=uuid.uuid4(),
            email=email,
            phone=phone,
            password_hash="temp_hash",
            full_name=full_name,
            role="patient",
            is_active=True
        )
        db.add(new_user)
        await db.flush()

        # Create patient
        new_patient = Patient(
            id=uuid.uuid4(),
            user_id=new_user.id,
            uhid=new_uhid,
            gender=gender,
            blood_group=blood_group
        )
        db.add(new_patient)
        await log_action(db, new_user.id, "REGISTER", "patient", new_patient.id, {"uhid": new_uhid, "name": full_name})
        await db.commit()

    return f"Patient registered successfully! UHID: {new_uhid}, Name: {full_name}"




@tool

async def update_patient(
    uhid:str,
    full_name:str="",
    phone:str="",
    email:str="",
    gender:str="",
    blood_group:str="",
    address:str="",
    emergency_contact_name:str="",
    emergency_contact_phone:str=""
)->str:
    """
    Update patient details. Only provided fields will be updated.
    """
    async with async_session() as db:
        stmt=select(Patient,User).join(User,Patient.user_id==User.id).where(Patient.uhid==uhid)
        result=await db.execute(stmt)
        row=result.first()

        if not row:
            return "Patient not found"

        patient,user=row

        if full_name:
            user.full_name=full_name
        if phone:
            user.phone=phone
        if email:
            user.email=email
        if gender:
            patient.gender=gender
        if blood_group:
            patient.blood_group=blood_group
        if address:
            patient.address=address
        if emergency_contact_name:
            patient.emergency_contact_name=emergency_contact_name
        if emergency_contact_phone:
            patient.emergency_contact_phone=emergency_contact_phone

        await log_action(db, user.id, "UPDATE", "patient", patient.id, {"uhid": uhid})
        await db.commit()

    return "Patient details updated successfully!"


@tool
async def add_beneficiary(patient_uhid: str, beneficiary_uhid: str, relationship: str) -> str:
    """Add a family member (beneficiary) to a patient. Relationship: spouse, child, parent, sibling, guardian, other."""
    from models.beneficiary import Beneficiary
    valid_relationships = ["spouse", "child", "parent", "sibling", "guardian", "other"]
    if relationship.lower() not in valid_relationships:
        return f"Invalid relationship. Use one of: {', '.join(valid_relationships)}"

    async with async_session() as db:
        # Find both patients
        pat_result = await db.execute(select(Patient).where(Patient.uhid == patient_uhid))
        patient = pat_result.scalars().first()
        if not patient:
            return f"Patient {patient_uhid} not found."

        ben_result = await db.execute(select(Patient).where(Patient.uhid == beneficiary_uhid))
        beneficiary = ben_result.scalars().first()
        if not beneficiary:
            return f"Beneficiary {beneficiary_uhid} not found. Register them first."

        # Check if already linked
        existing = await db.execute(
            select(Beneficiary).where(
                Beneficiary.patient_id == patient.id,
                Beneficiary.beneficiary_patient_id == beneficiary.id
            )
        )
        if existing.scalars().first():
            return f"{beneficiary_uhid} is already a beneficiary of {patient_uhid}."

        new_ben = Beneficiary(
            id=uuid.uuid4(),
            patient_id=patient.id,
            beneficiary_patient_id=beneficiary.id,
            relationship=relationship.lower()
        )
        db.add(new_ben)
        await log_action(db, patient.user_id, "ADD_BENEFICIARY", "beneficiary", new_ben.id, {"patient": patient_uhid, "beneficiary": beneficiary_uhid, "relationship": relationship})
        await db.commit()

    return f"Beneficiary added! {beneficiary_uhid} linked to {patient_uhid} as {relationship}."


@tool
async def get_my_beneficiaries(patient_uhid: str) -> str:
    """Get all beneficiaries (family members) linked to a patient."""
    from models.beneficiary import Beneficiary
    async with async_session() as db:
        result = await db.execute(
            select(Beneficiary, Patient, User)
            .join(Patient, Beneficiary.beneficiary_patient_id == Patient.id)
            .join(User, Patient.user_id == User.id)
            .where(
                Beneficiary.patient_id.in_(
                    select(Patient.id).where(Patient.uhid == patient_uhid)
                )
            )
        )
        rows = result.all()

    if not rows:
        return "No beneficiaries found."

    output = ""
    for ben, patient, user in rows:
        output += (
            f"UHID: {patient.uhid}\n"
            f"Name: {user.full_name}\n"
            f"Relationship: {ben.relationship}\n"
            f"Email: {user.email}\n"
            f"Phone: {user.phone}\n"
            f"Gender: {patient.gender}\n"
            f"Blood Group: {patient.blood_group}\n"
            f"DOB: {patient.date_of_birth}\n"
            f"Address: {patient.address}\n"
            f"Emergency Contact: {patient.emergency_contact_name} ({patient.emergency_contact_phone})\n\n"
        )
    return output