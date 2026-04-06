from services.notifications.email_adapter import send_email
import asyncio


async def notify_booking(patient_email, patient_name, doctor_name, date, time, uhid):
    """Notify patient that their appointment is booked."""
    subject = "Appointment Confirmed - HMS Hospital"
    body = f"""Dear {patient_name},

Your appointment has been confirmed.

Doctor: {doctor_name}
Date: {date}
Time: {time}
UHID: {uhid}

Please arrive 15 minutes before your appointment time.

Thank you,
HMS Hospital"""

    asyncio.create_task(send_email(patient_email, subject, body))


async def notify_cancellation(patient_email, patient_name, doctor_name, date, time):
    """Notify patient that their appointment is cancelled."""
    subject = "Appointment Cancelled - HMS Hospital"
    body = f"""Dear {patient_name},

Your appointment has been cancelled.

Doctor: {doctor_name}
Date: {date}
Time: {time}

If you did not request this cancellation, please contact the hospital.

Thank you,
HMS Hospital"""

    asyncio.create_task(send_email(patient_email, subject, body))


async def notify_checkin(patient_email, patient_name, doctor_name, estimated_wait):
    """Notify patient that they have been checked in."""
    subject = "Checked In - HMS Hospital"
    body = f"""Dear {patient_name},

You have been successfully checked in.

Doctor: {doctor_name}
Estimated Wait: {estimated_wait} minutes

Please wait in the designated area. You will be called when it's your turn.

Thank you,
HMS Hospital"""

    asyncio.create_task(send_email(patient_email, subject, body))


async def notify_feedback(patient_email, patient_name, doctor_name):
    """Ask patient for feedback after appointment completion."""
    subject = "How was your visit? - HMS Hospital"
    body = f"""Dear {patient_name},

Your appointment with {doctor_name} has been completed.

We'd love to hear about your experience! Please rate your visit through our chatbot.

Thank you for choosing HMS Hospital."""

    asyncio.create_task(send_email(patient_email, subject, body))


async def notify_no_show(patient_email, patient_name, doctor_name, risk_score):
    """Notify patient about no-show and risk score increase."""
    subject = "Missed Appointment - HMS Hospital"
    body = f"""Dear {patient_name},

You missed your appointment with {doctor_name}.

Your risk score has been increased to {risk_score}. Repeated no-shows may affect your ability to book appointments.

Please contact the hospital if this was an error.

Thank you,
HMS Hospital"""

    asyncio.create_task(send_email(patient_email, subject, body))


async def notify_session_cancelled(patient_email, patient_name, doctor_name, date):
    """Notify patient that the doctor's session has been cancelled."""
    subject = "Session Cancelled - HMS Hospital"
    body = f"""Dear {patient_name},

We regret to inform you that {doctor_name}'s session on {date} has been cancelled.

Please rebook your appointment at your convenience.

We apologize for the inconvenience.

Thank you,
HMS Hospital"""

    asyncio.create_task(send_email(patient_email, subject, body))
