import uuid                                                                                                                  
from datetime import datetime
from sqlalchemy import Column, Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID                                                                                
from models.base import Base
                                                                                                                                
                                                                                                                            
class Rating(Base):                                                                                                          
    __tablename__ = "ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)                                                      
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), unique=True, nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)                                           
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)                                         
    rating = Column(Integer, nullable=False)                                                                                 
    review = Column(Text, nullable=True)                                                                                       
    sentiment_score = Column(Float, nullable=True)                                                                           
    created_at = Column(DateTime, default=datetime.utcnow) 