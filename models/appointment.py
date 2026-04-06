import uuid
from sqlalchemy import Column, String, Integer, Boolean, Text, Time, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from models.base import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    booked_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    slot_number = Column(Integer, nullable=False)
    slot_position = Column(Integer, default=1)
    slot_time = Column(Time, nullable=False)
    status = Column(String(20), default="booked")
    priority = Column(String(20), default="NORMAL")
    is_emergency = Column(Boolean, default=False)
    cancel_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    checked_in_at = Column(DateTime, nullable=True)
    called_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
