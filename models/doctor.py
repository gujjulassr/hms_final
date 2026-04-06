import uuid
from sqlalchemy import Column, String, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID                                                                                
from models.base import Base
                                                                                                                                
                
class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)                                                      
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    specialization = Column(String(100), nullable=False)                                                                       
    qualification = Column(String(255), nullable=True)
    consultation_fee = Column(Integer, default=0)                                                                              
    avg_rating = Column(Float, default=0.0)
    total_ratings = Column(Integer, default=0)  