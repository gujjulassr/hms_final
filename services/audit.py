import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from models.audit_log import AuditLog


async def log_action(db: AsyncSession, user_id, action, target_type, target_id, details=None):
    """Log an action to the audit trail.

    Actions: BOOK, CANCEL, CHECKIN, CALL, COMPLETE, NO_SHOW, REGISTER,
             UPDATE, EMERGENCY, SET_PRIORITY, CREATE_SESSION, ACTIVATE_SESSION,
             COMPLETE_SESSION, EXTEND_SESSION, CANCEL_SESSION

    Target types: appointment, patient, user, session
    """
    audit = AuditLog(
        id=uuid.uuid4(),
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        created_at=datetime.now()
    )
    db.add(audit)
