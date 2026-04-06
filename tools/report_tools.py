from langchain_core.tools import tool
from sqlalchemy import select
from models.appointment import Appointment
from models.patient import Patient
from models.session import Session
from models.doctor import Doctor
from models.user import User
from models.rating import Rating
from config.database import AsyncSessionLocal as async_session
from fpdf import FPDF, XPos, YPos
from datetime import datetime, date
from services.documents.service import deliver_document
import os

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def clean(text):
    if text is None:
        return "N/A"
    return str(text).encode('latin-1', 'replace').decode('latin-1')


@tool
async def generate_patient_report(patient_uhid: str) -> str:
    """Generate a PDF report for a patient with their details and appointment history."""
    async with async_session() as db:
        # Get patient details
        pat_result = await db.execute(
            select(Patient, User).join(User, Patient.user_id == User.id).where(Patient.uhid == patient_uhid)
        )
        pat_row = pat_result.first()
        if not pat_row:
            return f"Patient {patient_uhid} not found."
        patient, user = pat_row

        # Get appointments
        appt_result = await db.execute(
            select(Appointment, Session, Doctor, User)
            .join(Session, Appointment.session_id == Session.id)
            .join(Doctor, Session.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(Appointment.patient_id == patient.id)
            .order_by(Session.session_date.desc(), Appointment.slot_time.desc())
        )
        appointments = appt_result.all()

        # Get ratings given by this patient
        rating_result = await db.execute(
            select(Rating, Doctor, User)
            .join(Doctor, Rating.doctor_id == Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(Rating.patient_id == patient.id)
        )
        ratings = rating_result.all()

    # Build PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font('Helvetica', 'B', 20)
    pdf.cell(0, 12, 'Patient Report', align='C')
    pdf.ln(15)

    # Patient Info
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_fill_color(230, 230, 250)
    pdf.cell(0, 9, 'Patient Information', fill=True)
    pdf.ln(12)

    pdf.set_font('Helvetica', '', 11)
    info = [
        ('UHID', patient.uhid),
        ('Name', user.full_name),
        ('Email', user.email),
        ('Phone', user.phone),
        ('Gender', patient.gender),
        ('Blood Group', patient.blood_group),
        ('Date of Birth', str(patient.date_of_birth)),
        ('Address', patient.address),
        ('Emergency Contact', f"{patient.emergency_contact_name} ({patient.emergency_contact_phone})"),
        ('Risk Score', str(patient.risk_score)),
    ]
    for label, value in info:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(50, 7, clean(label) + ':')
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 7, clean(value))
        pdf.ln()

    pdf.ln(8)

    # Appointments
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_fill_color(230, 230, 250)
    pdf.cell(0, 9, f'Appointment History ({len(appointments)} records)', fill=True)
    pdf.ln(12)

    if appointments:
        # Table header
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(200, 200, 220)
        pdf.cell(35, 7, 'Date', fill=True)
        pdf.cell(20, 7, 'Time', fill=True)
        pdf.cell(40, 7, 'Doctor', fill=True)
        pdf.cell(25, 7, 'Status', fill=True)
        pdf.cell(15, 7, 'Slot', fill=True)
        pdf.cell(55, 7, 'Notes', fill=True)
        pdf.ln()

        pdf.set_font('Helvetica', '', 9)
        for appt, session, doctor, doc_user in appointments:
            pdf.cell(35, 6, clean(str(session.session_date)))
            pdf.cell(20, 6, clean(str(appt.slot_time)))
            pdf.cell(40, 6, clean(doc_user.full_name))
            pdf.cell(25, 6, clean(appt.status))
            pdf.cell(15, 6, clean(str(appt.slot_number)))
            pdf.cell(55, 6, clean(str(appt.notes)[:30] if appt.notes else ''))
            pdf.ln()
    else:
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 7, 'No appointments found.')
        pdf.ln()

    pdf.ln(8)

    # Ratings
    if ratings:
        pdf.set_font('Helvetica', 'B', 14)
        pdf.set_fill_color(230, 230, 250)
        pdf.cell(0, 9, 'Ratings Given', fill=True)
        pdf.ln(12)

        for rating, doctor, doc_user in ratings:
            pdf.set_font('Helvetica', 'B', 10)
            pdf.cell(0, 7, clean(f"Dr. {doc_user.full_name} - {rating.rating}/5"))
            pdf.ln()
            if rating.review:
                pdf.set_font('Helvetica', '', 9)
                pdf.multi_cell(190, 5, clean(rating.review))
            pdf.ln(3)

    # Footer
    pdf.ln(10)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.cell(0, 5, clean(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} | HMS Chatbot System"))

    # Save
    filename = f"patient_{patient_uhid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)
    pdf.output(filepath)

    link = deliver_document(filepath, filename)
    return f"Patient report generated: {link}"


@tool
async def generate_session_report(doctor_name: str) -> str:
    """Generate a PDF report for a doctor's today's sessions with all appointments."""
    async with async_session() as db:
        # Find doctor
        doc_result = await db.execute(
            select(Doctor, User).join(User, Doctor.user_id == User.id).where(User.full_name.ilike(f"%{doctor_name}%"))
        )
        doc_row = doc_result.first()
        if not doc_row:
            return f"Doctor {doctor_name} not found."
        doctor, doc_user = doc_row

        # Get today's sessions
        session_result = await db.execute(
            select(Session).where(
                Session.doctor_id == doctor.id,
                Session.session_date == date.today()
            ).order_by(Session.start_time)
        )
        sessions = session_result.scalars().all()

        if not sessions:
            return f"No sessions found for Dr. {doc_user.full_name} today."

        # Get appointments for each session
        session_data = []
        for sess in sessions:
            appt_result = await db.execute(
                select(Appointment, Patient, User)
                .join(Patient, Appointment.patient_id == Patient.id)
                .join(User, Patient.user_id == User.id)
                .where(Appointment.session_id == sess.id)
                .order_by(Appointment.slot_number)
            )
            appts = appt_result.all()
            session_data.append((sess, appts))

    # Build PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font('Helvetica', 'B', 20)
    pdf.cell(0, 12, 'Session Report', align='C')
    pdf.ln(10)
    pdf.set_font('Helvetica', '', 12)
    pdf.cell(0, 8, clean(f"Doctor: {doc_user.full_name} | Date: {date.today()}"), align='C')
    pdf.ln(15)

    for sess, appts in session_data:
        # Session header
        pdf.set_font('Helvetica', 'B', 13)
        pdf.set_fill_color(230, 230, 250)
        pdf.cell(0, 9, clean(f"Session: {sess.start_time} - {sess.end_time} | Status: {sess.status}"), fill=True)
        pdf.ln(10)

        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, clean(f"Slots: {sess.total_slots} | Duration: {sess.slot_duration_minutes}min | Max/Slot: {sess.max_per_slot} | Delay: {sess.delay_minutes}min | Overtime: {sess.overtime_minutes}min"))
        pdf.ln(10)

        if appts:
            # Stats
            total = len(appts)
            completed = sum(1 for a, _, _ in appts if a.status == 'completed')
            no_show = sum(1 for a, _, _ in appts if a.status == 'no_show')
            cancelled = sum(1 for a, _, _ in appts if a.status == 'cancelled')
            pending = total - completed - no_show - cancelled

            pdf.set_font('Helvetica', 'B', 10)
            pdf.cell(0, 6, clean(f"Total: {total} | Completed: {completed} | No-Show: {no_show} | Cancelled: {cancelled} | Pending: {pending}"))
            pdf.ln(8)

            # Table
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_fill_color(200, 200, 220)
            pdf.cell(15, 7, 'Slot', fill=True)
            pdf.cell(20, 7, 'Time', fill=True)
            pdf.cell(35, 7, 'UHID', fill=True)
            pdf.cell(40, 7, 'Name', fill=True)
            pdf.cell(25, 7, 'Status', fill=True)
            pdf.cell(20, 7, 'Priority', fill=True)
            pdf.cell(35, 7, 'Notes', fill=True)
            pdf.ln()

            pdf.set_font('Helvetica', '', 9)
            for appt, patient, pat_user in appts:
                pdf.cell(15, 6, clean(str(appt.slot_number)))
                pdf.cell(20, 6, clean(str(appt.slot_time)))
                pdf.cell(35, 6, clean(patient.uhid))
                pdf.cell(40, 6, clean(pat_user.full_name))
                pdf.cell(25, 6, clean(appt.status))
                pdf.cell(20, 6, clean(appt.priority))
                pdf.cell(35, 6, clean(str(appt.notes)[:20] if appt.notes else ''))
                pdf.ln()
        else:
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(0, 7, 'No appointments in this session.')
            pdf.ln()

        pdf.ln(8)

    # Footer
    pdf.set_font('Helvetica', 'I', 8)
    pdf.cell(0, 5, clean(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} | HMS Chatbot System"))

    filename = f"session_{doc_user.full_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)
    pdf.output(filepath)

    link = deliver_document(filepath, filename)
    return f"Session report generated: {link}"
