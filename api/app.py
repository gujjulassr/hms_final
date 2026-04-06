import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import chat, reports, auth, patient_dashboard, doctor_dashboard, admin_dashboard
from services.scheduler import run_scheduler

app = FastAPI(title="HMS Chatbot API", version="1.0.0")

# Allow any frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(patient_dashboard.router, prefix="/api/patient", tags=["Patient Dashboard"])
app.include_router(doctor_dashboard.router, prefix="/api/doctor", tags=["Doctor Dashboard"])
app.include_router(admin_dashboard.router, prefix="/api/admin", tags=["Admin Dashboard"])


@app.on_event("startup")
async def startup():
    asyncio.create_task(run_scheduler())


@app.get("/")
async def root():
    return {"message": "HMS Chatbot API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
