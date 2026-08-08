"""
email_service.py — Email verification and password reset.
Uses Gmail SMTP (free) or any SMTP server.

Setup:
    setx CMT_EMAIL_ADDRESS "your-gmail@gmail.com"
    setx CMT_EMAIL_PASSWORD "your-app-password"

For Gmail, you need an App Password (not your regular password):
    1. Go to https://myaccount.google.com/apppasswords
    2. Generate one for "Mail"
    3. Use that as CMT_EMAIL_PASSWORD
"""

import os
import smtplib
import secrets
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.environ.get("CMT_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("CMT_SMTP_PORT", "587"))


def _get_credentials():
    addr = os.environ.get("CMT_EMAIL_ADDRESS")
    pw = os.environ.get("CMT_EMAIL_PASSWORD")
    if not addr or not pw:
        raise EnvironmentError(
            "Email not configured. Set CMT_EMAIL_ADDRESS and CMT_EMAIL_PASSWORD.\n"
            "For Gmail: use an App Password from https://myaccount.google.com/apppasswords"
        )
    return addr, pw


def send_email(to_email: str, subject: str, html_body: str):
    """Send an HTML email."""
    from_addr, password = _get_credentials()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"CMT SA Voice Assistant <{from_addr}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(from_addr, password)
        server.send_message(msg)


def send_verification_email(to_email: str, code: str, app_url: str = "http://localhost:8501"):
    """Send a verification code email."""
    html = f"""
    <div style="font-family:Arial; max-width:500px; margin:auto; padding:20px;">
        <h2 style="color:#1D9E75;">🇿🇦 CMT SA Voice Assistant</h2>
        <p>Your verification code is:</p>
        <div style="background:#0D1B2A; color:#00C9A7; font-size:32px; padding:20px;
                    text-align:center; border-radius:8px; letter-spacing:8px; font-family:monospace;">
            {code}
        </div>
        <p style="color:#666; font-size:12px; margin-top:20px;">
            This code expires in 15 minutes. If you didn't request this, ignore this email.
        </p>
    </div>
    """
    send_email(to_email, "CMT SA Voice — Verify your email", html)


def send_password_reset_email(to_email: str, code: str):
    """Send a password reset code email."""
    html = f"""
    <div style="font-family:Arial; max-width:500px; margin:auto; padding:20px;">
        <h2 style="color:#1D9E75;">🇿🇦 CMT SA Voice Assistant</h2>
        <p>Your password reset code is:</p>
        <div style="background:#0D1B2A; color:#FFB703; font-size:32px; padding:20px;
                    text-align:center; border-radius:8px; letter-spacing:8px; font-family:monospace;">
            {code}
        </div>
        <p style="color:#666; font-size:12px; margin-top:20px;">
            This code expires in 15 minutes. If you didn't request this, ignore this email.
        </p>
    </div>
    """
    send_email(to_email, "CMT SA Voice — Password Reset", html)


def generate_code() -> str:
    """Generate a 6-digit verification code."""
    return f"{secrets.randbelow(900000) + 100000}"
