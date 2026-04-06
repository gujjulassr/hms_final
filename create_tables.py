import asyncio                                                                                                                 
from sqlalchemy.ext.asyncio import create_async_engine
from config.settings import DATABASE_URL
from models.base import Base                                                                                                   
from models.user import User
from models.doctor import Doctor                                                                                               
from models.patient import Patient
from models.beneficiary import Beneficiary
from models.session import Session
from models.appointment import Appointment
from models.rating import Rating
from models.audit_log import AuditLog                                                                                          

                                                                                                                                
async def create_tables():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()                                                                                                     
    print("All tables created successfully!")
                                                                                                                                
                
asyncio.run(create_tables())
