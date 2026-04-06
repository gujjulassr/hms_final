from fastapi import APIRouter
from fastapi.responses import FileResponse
from langchain_core.messages import HumanMessage
from agent.graph import app
import os

router = APIRouter()

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "reports")


@router.get("/patient/{patient_uhid}")
async def get_patient_report(patient_uhid: str):
    """Generate and download a patient report PDF."""
    result = await app.ainvoke({
        "messages": [HumanMessage(content=f"generate my report for {patient_uhid}")],
        "role": "patient"
    })

    reply = result["messages"][-1].content

    # Find the generated file
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.startswith(f"patient_{patient_uhid}")],
        reverse=True
    )
    if files:
        filepath = os.path.join(REPORTS_DIR, files[0])
        return FileResponse(filepath, media_type="application/pdf", filename=files[0])

    return {"error": "Report generation failed", "details": reply}


@router.get("/session/{doctor_name}")
async def get_session_report(doctor_name: str):
    """Generate and download a session report PDF."""
    result = await app.ainvoke({
        "messages": [HumanMessage(content=f"generate session report for {doctor_name}")],
        "role": "doctor"
    })

    reply = result["messages"][-1].content

    # Find the generated file
    doctor_file = doctor_name.replace(" ", "_")
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.startswith(f"session_{doctor_file}")],
        reverse=True
    )
    if files:
        filepath = os.path.join(REPORTS_DIR, files[0])
        return FileResponse(filepath, media_type="application/pdf", filename=files[0])

    return {"error": "Report generation failed", "details": reply}
