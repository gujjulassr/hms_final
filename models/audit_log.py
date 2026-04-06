import uuid                                                                                                                    
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
                                                                                                                                
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)                                               
    action = Column(String(50), nullable=False)                                                                                
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)                                                                     
    details = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)  