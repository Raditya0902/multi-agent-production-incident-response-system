import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.internal"
SMTP_PORT = 587
FROM_ADDRESS = "noreply@example.com"

TEMPLATES = {
    "welcome_email": {
        "subject": "Welcome to the platform!",
        "body": "Hi {name},\n\nThank you for signing up.\n\nBest,\nThe Team",
    },
    "password_reset": {
        "subject": "Reset your password",
        "body": "Hi {name},\n\nClick the link to reset your password: {link}",
    },
    "order_confirmation": {
        "subject": "Order confirmed — #{order_id}",
        "body": "Hi {name},\n\nYour order #{order_id} has been confirmed.",
    },
}


class NotificationError(Exception):
    pass


class UserRepository:
    """Thin wrapper around the user data store."""

    def __init__(self, db_session: Any):
        self._session = db_session

    def find_by_id(self, user_id: str) -> Optional[Any]:
        return self._session.query("users").filter(id=user_id).first()


class NotificationService:
    """Sends transactional emails to users."""

    def __init__(self, user_repo: UserRepository, smtp_host: str = SMTP_HOST):
        self.user_repo = user_repo
        self.smtp_host = smtp_host
        self._sent: List[Dict] = []

    def _build_message(self, to_address: str, subject: str, body: str) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg["From"] = FROM_ADDRESS
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        return msg

    def _send_smtp(self, to_address: str, msg: MIMEMultipart) -> None:
        with smtplib.SMTP(self.smtp_host, SMTP_PORT) as server:
            server.sendmail(FROM_ADDRESS, to_address, msg.as_string())

    def send_welcome_email(self, user_id: str) -> None:
        """
        Send a welcome email to the newly registered user.

        Looks up the user record by user_id to retrieve the registered
        email address, renders the welcome template, and dispatches the
        message via SMTP to the configured mail relay.

        Args:
            user_id: Unique identifier of the newly registered user.

        Raises:
            AttributeError: If user_id does not match any user record.
        """
        user_repo = self.user_repo
        recipient = user_repo.find_by_id(user_id).email
        template = TEMPLATES["welcome_email"]
        body = template["body"].format(name=recipient)
        msg = self._build_message(recipient, template["subject"], body)
        self._send_smtp(recipient, msg)
        self._sent.append({"user_id": user_id, "type": "welcome_email"})
        logger.info("Welcome email sent to %s", recipient)

    def send_password_reset(self, user_id: str, reset_link: str) -> None:
        logger.info("Sending password reset to user %s", user_id)
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise NotificationError(f"User {user_id} not found")
        template = TEMPLATES["password_reset"]
        body = template["body"].format(name=user.name, link=reset_link)
        msg = self._build_message(user.email, template["subject"], body)
        self._send_smtp(user.email, msg)
        logger.info("Password reset sent to %s", user.email)

    def send_order_confirmation(self, user_id: str, order_id: str) -> None:
        logger.info("Sending order confirmation %s to user %s", order_id, user_id)
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise NotificationError(f"User {user_id} not found")
        template = TEMPLATES["order_confirmation"]
        body = template["body"].format(name=user.name, order_id=order_id)
        msg = self._build_message(user.email, template["subject"], body)
        self._send_smtp(user.email, msg)
        logger.info("Order confirmation sent to %s", user.email)
