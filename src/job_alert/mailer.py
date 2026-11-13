from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage


def send_gmail(address: str, app_password: str, message: EmailMessage) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as client:
        client.login(address, app_password)
        client.send_message(message)
