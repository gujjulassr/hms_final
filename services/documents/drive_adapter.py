from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config.settings import GOOGLE_DRIVE_FOLDER_ID
import logging
import os

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'hms_multi_agent.json')


def get_drive_service():
    """Create Google Drive service using service account."""
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=credentials)


def upload_to_drive(file_path, filename=None):
    """Upload a file to Google Drive and return shareable link."""
    try:
        service = get_drive_service()

        if not filename:
            filename = os.path.basename(file_path)

        file_metadata = {
            'name': filename,
            'parents': [GOOGLE_DRIVE_FOLDER_ID]
        }

        media = MediaFileUpload(file_path, mimetype='application/pdf')

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()

        # Make file accessible via link
        service.permissions().create(
            fileId=file['id'],
            body={'type': 'anyone', 'role': 'reader'},
            supportsAllDrives=True
        ).execute()

        link = file.get('webViewLink', '')
        logger.info(f"Uploaded {filename} to Drive: {link}")
        return link

    except Exception as e:
        logger.error(f"Drive upload failed: {e}")
        return None
