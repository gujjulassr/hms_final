import uuid
from sqlalchemy import Column, Date, String, Integer, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID                                                                                
from models.base import Base
                                

class Patient(Base):
      __tablename__ = "patients"

      id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)                                                      
      user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
      uhid = Column(String(50), unique=True, nullable=False)                                                                     
      blood_group = Column(String(10), nullable=True)                                                                            
      gender = Column(String(10), nullable=True)
      date_of_birth = Column(Date, nullable=True)                                                                                
      address = Column(Text, nullable=True)
      emergency_contact_name = Column(String(255), nullable=True)                                                                
      emergency_contact_phone = Column(String(20), nullable=True)
      risk_score = Column(Integer, default=0)                                                                                    
      risk_notes = Column(Text, nullable=True)