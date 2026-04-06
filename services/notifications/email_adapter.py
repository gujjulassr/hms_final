import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config.settings import SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM_NAME
import logging

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body: str):
    """Send an email via Gmail SMTP. Fire-and-forget — failures are logged, not raised."""
    try:
        msg = MIMEMultipart()
        msg["From"] = f"{EMAIL_FROM_NAME} <{SMTP_USERNAME}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USERNAME,
            password=SMTP_PASSWORD,
            start_tls=True
        )
        logger.info(f"Email sent to {to}: {subject}")
    except Exception as e:
        logger.warning(f"Email failed to {to}: {e}")
