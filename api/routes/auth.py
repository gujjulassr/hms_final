from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from models.user import User
from models.patient import Patient
from models.doctor import Doctor
from config.database import AsyncSessionLocal as async_session
from services.auth import hash_password, verify_password, create_token
import uuid
from datetime import datetime

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    phone: str


class TokenResponse(BaseModel):
    token: str
    role: str
    full_name: str


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    async with async_session() as db:
        result = await db.execute(
            select(User).where(User.email == request.email, User.is_active == True)
        )
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        if not verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Wrong password")

        token = create_token(str(user.id), user.email, user.role)

    return TokenResponse(token=token, role=user.role, full_name=user.full_name)


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    async with async_session() as db:
        # Check if email already exists
        existing = await db.execute(select(User).where(User.email == request.email))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        new_user = User(
            id=uuid.uuid4(),
            email=request.email,
            password_hash=hash_password(request.password),
            full_name=request.full_name,
            phone=request.phone,
            role="patient",
            is_active=True
        )
        db.add(new_user)
        await db.flush()

        # Create patient profile
        # Generate UHID
        pat_result = await db.execute(select(Patient).order_by(Patient.uhid.desc()))
        last_patient = pat_result.scalars().first()
        if last_patient:
            last_number = int(last_patient.uhid.split("-")[-1])
            new_uhid = f"HMS-{datetime.now().year}-{str(last_number + 1).zfill(5)}"
        else:
            new_uhid = f"HMS-{datetime.now().year}-00001"

        new_patient = Patient(
            id=uuid.uuid4(),
            user_id=new_user.id,
            uhid=new_uhid
        )
        db.add(new_patient)
        await db.commit()

        token = create_token(str(new_user.id), new_user.email, new_user.role)

    return TokenResponse(token=token, role="patient", full_name=request.full_name)
