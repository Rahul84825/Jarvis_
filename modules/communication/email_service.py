import os
import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from typing import Dict, List, Any, Optional
from config import config

logger = logging.getLogger("Jarvis.EmailService")

class EmailService:
    """Full-featured Email Client supporting IMAP reading, SMTP sending, and AI summarization.
    Operates in live mode with valid credentials or graceful simulated mode for safe demonstration.
    """

    def __init__(self):
        self.imap_server = getattr(config, "email_imap_server", os.getenv("EMAIL_IMAP_SERVER", "imap.gmail.com"))
        self.smtp_server = getattr(config, "email_smtp_server", os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com"))
        self.email_address = getattr(config, "email_address", os.getenv("EMAIL_ADDRESS", ""))
        self.email_password = getattr(config, "email_password", os.getenv("EMAIL_PASSWORD", ""))
        self.is_configured = bool(self.email_address and self.email_password)

        if not self.is_configured:
            logger.info("Email credentials not configured in .env. Operating in simulated intelligence mode.")

    def get_unread_emails(self, limit: int = 5) -> List[Dict[str, str]]:
        """Fetches unread emails from the inbox."""
        if not self.is_configured:
            logger.info("Generating demo email inbox summary (unconfigured email credentials).")
            return [
                {
                    "id": "1",
                    "sender": "Project Team <team@workspace.io>",
                    "subject": "Sprint Review: Jarvis 2.0 Deployment Ready",
                    "date": "Today, 10:15 AM",
                    "snippet": "The new agentic reasoning and multi-device modules have passed preliminary automated test suites.",
                    "is_demo": True
                },
                {
                    "id": "2",
                    "sender": "Security Watch <alerts@security.org>",
                    "subject": "System Security Notice: Voice Core Online",
                    "date": "Today, 08:30 AM",
                    "snippet": "All micro-services and speech endpoints have been verified and secured.",
                    "is_demo": True
                }
            ]

        results = []
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.email_password)
            mail.select("inbox")

            status, messages = mail.search(None, 'UNSEEN')
            if status != "OK":
                return []

            mail_ids = messages[0].split()
            for msg_id in mail_ids[-limit:]:
                status, data = mail.fetch(msg_id, '(RFC822)')
                if status != "OK":
                    continue

                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Subject decode
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8", errors="ignore")
                        
                        # Sender decode
                        sender = msg.get("From", "Unknown Sender")

                        # Body snippet extraction
                        body_snippet = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                if content_type == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body_snippet = payload.decode(errors="ignore")[:200]
                                        break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body_snippet = payload.decode(errors="ignore")[:200]

                        results.append({
                            "id": msg_id.decode(),
                            "sender": sender,
                            "subject": subject,
                            "date": msg.get("Date", ""),
                            "snippet": body_snippet.strip().replace("\n", " "),
                            "is_demo": False
                        })
            mail.close()
            mail.logout()
        except Exception as e:
            logger.error(f"Error checking emails: {e}")
            return [{"error": f"Email check failed: {str(e)}"}]

        return results

    def send_email(self, to_address: str, subject: str, body: str) -> Dict[str, Any]:
        """Sends an email via SMTP."""
        if not self.is_configured:
            logger.info(f"[SIMULATED SEND] To: {to_address} | Subject: '{subject}' | Body: {body}")
            return {
                "success": True,
                "simulated": True,
                "message": f"Email drafted and simulated to {to_address} with subject '{subject}'."
            }

        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to_address
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            server = smtplib.SMTP_SSL(self.smtp_server, 465)
            server.login(self.email_address, self.email_password)
            server.sendmail(self.email_address, to_address, msg.as_string())
            server.quit()

            logger.info(f"Email successfully sent to {to_address}")
            return {
                "success": True,
                "message": f"Email sent successfully to {to_address}."
            }
        except Exception as e:
            logger.error(f"Failed to send email to {to_address}: {e}")
            return {
                "success": False,
                "message": f"Failed to send email: {str(e)}"
            }

# Singleton instance
email_service = EmailService()
