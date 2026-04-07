import os
from dotenv import load_dotenv

load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

DATABASE_URL=os.getenv("DATABASE_URL")
DEBUG=os.getenv("DEBUG","False").lower()=="true"
MONGODB_URI=os.getenv("MONGODB_URI")
MONGODB_DB=os.getenv("MONGODB_DB")

JWT_SECRET = os.getenv("JWT_SECRET")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "HMS Hospital")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

