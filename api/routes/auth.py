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


# ==========================================
# GOOGLE OAUTH
# ==========================================

from config.settings import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI
from fastapi.responses import RedirectResponse
import httpx


@router.get("/google/url")
async def google_login_url():
    """Returns the Google OAuth login URL."""
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={GOOGLE_REDIRECT_URI}&"
        "response_type=code&"
        "scope=openid email profile&"
        "access_type=offline"
    )
    return {"url": url}


@router.get("/google/callback")
async def google_callback(code: str):
    """Google sends user here after login. Exchange code for user info."""

    # Step 1: Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )
        if token_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get Google token")
        tokens = token_response.json()

        # Step 2: Get user info from Google
        user_info_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        if user_info_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        google_user = user_info_response.json()

    # Step 3: Check if user exists in our database
    email = google_user["email"]
    name = google_user.get("name", email)
    google_id = google_user["id"]

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()

        if not user:
            # New user — create patient account
            new_user = User(
                id=uuid.uuid4(),
                email=email,
                phone="",
                password_hash=hash_password(str(uuid.uuid4())),
                full_name=name,
                role="patient",
                google_id=google_id,
                is_active=True
            )
            db.add(new_user)
            await db.flush()

            # Generate UHID
            pat_result = await db.execute(select(Patient).order_by(Patient.uhid.desc()))
            last = pat_result.scalars().first()
            if last:
                num = int(last.uhid.split("-")[-1]) + 1
            else:
                num = 1
            uhid = f"HMS-{datetime.now().year}-{str(num).zfill(5)}"

            new_patient = Patient(
                id=uuid.uuid4(),
                user_id=new_user.id,
                uhid=uhid
            )
            db.add(new_patient)
            await db.commit()
            user = new_user

        else:
            # Existing user — update google_id if not set
            if not user.google_id:
                user.google_id = google_id
                await db.commit()

        token = create_token(str(user.id), user.email, user.role)

    # Step 4: Redirect to Streamlit with token
    return RedirectResponse(url=f"http://localhost:8501?token={token}&role={user.role}&name={user.full_name}")
