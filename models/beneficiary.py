import uuid                                 
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from models.base import Base                                                                                                   

                                                                                                                                
class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    beneficiary_patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    relationship = Column(String(50), nullable=False)  