import uuid
from datetime import datetime
from sqlalchemy import Column,String,Boolean,DateTime
from sqlalchemy.dialects.postgresql import UUID
from models.base import Base



class User(Base):
    __tablename__ = "users"
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    email=Column(String(255),unique=True,nullable=False)
    phone=Column(String(20),nullable=True)
    password_hash=Column(String(255),nullable=False)
    full_name=Column(String(255),nullable=False)
    role=Column(String(25),nullable=False)
    google_id=Column(String(255),nullable=True)
    is_active=Column(Boolean,default=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)

