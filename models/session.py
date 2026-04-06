import uuid                                                                                                                    
from sqlalchemy import Column, String, Integer, Date, Time, Text, ForeignKey                                                   
from sqlalchemy.dialects.postgresql import UUID
from models.base import Base                                                                                                   
                
                                                                                                                                
class Session(Base):
    __tablename__ = "sessions"                                                                                                 
                
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)
    session_date = Column(Date, nullable=False)                                                                                
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)                                                                                    
    slot_duration_minutes = Column(Integer, default=15)
    max_per_slot = Column(Integer, default=2)
    total_slots = Column(Integer, nullable=False)                                                                              
    status = Column(String(20), default="scheduled")
    delay_minutes = Column(Integer, default=0)                                                                                 
    overtime_minutes = Column(Integer, default=0)
    notes = Column(Text, nullable=True)  