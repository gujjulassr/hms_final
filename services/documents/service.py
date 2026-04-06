from services.documents.drive_adapter import upload_to_drive
import logging

logger = logging.getLogger(__name__)


def deliver_document(file_path, filename=None):
    """Deliver a document using the configured adapter. Currently uses Google Drive."""
    link = upload_to_drive(file_path, filename)
    if link:
        return link
    # Fallback — return local path
    logger.warning(f"Drive upload failed, returning local path: {file_path}")
    return file_path
