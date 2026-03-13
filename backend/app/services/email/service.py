import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "console").lower()
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "no-reply@entscheid.local")

def send_email(to: str, subject: str, html: str, text: str):
    if EMAIL_PROVIDER == "console":
        print(f"\n{'='*50}")
        print(f"EMAIL MOCK (Console Provider)")
        print(f"TO: {to}")
        print(f"SUBJECT: {subject}")
        print(f"BODY:\n{text}")
        print(f"{'='*50}\n")
        return True

    elif EMAIL_PROVIDER == "smtp":
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM
            msg["To"] = to

            part1 = MIMEText(text, "plain")
            part2 = MIMEText(html, "html")
            msg.attach(part1)
            msg.attach(part2)

            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
            server.starttls()
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, to, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {e}")
            return False
    else:
        logger.error(f"Unknown EMAIL_PROVIDER: {EMAIL_PROVIDER}")
        return False
