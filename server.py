# --- Todo App Auth Helper ---
import requests

_todo_token = None

def todo_login(email: str, password: str) -> str:
    """Login to Todo app and return access token."""
    global _todo_token
    url = "http://127.0.0.1:8000/login"
    try:
        res = requests.post(url, json={"email": email, "password": password})
        data = res.json()
        if "access_token" in data:
            _todo_token = data["access_token"]
            return _todo_token
        else:
            raise Exception(data.get("detail", "Login failed"))
    except Exception as e:
        raise Exception(f"Login error: {e}")

def get_auth_header():
    if not _todo_token:
        raise Exception("Not logged in. Please call todo_login first.")
    return {"Authorization": f"Bearer {_todo_token}"}

from mcp.server.fastmcp import FastMCP
from datetime import datetime
import random

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Union, List, Dict
from time import sleep
import re
import asyncio


mcp = FastMCP("My Python MCP Server")


# ── Tool 1: Get current date & time ──────
@mcp.tool()
def get_current_time() -> str:
    """Returns the current date and time."""
    return f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


# ── Tool 2: Calculator ────────────────────
@mcp.tool()
def calculate(expression: str) -> str:
    """
    Evaluate a simple math expression.
    Example: '2 + 2', '10 * 5', '100 / 4'
    """
    try:
        # Safe eval - only allows math operations
        allowed = {k: v for k, v in vars(__builtins__).items()
                   if k in ('abs', 'round', 'min', 'max', 'sum', 'pow')}
        result = eval(expression, {"__builtins__": allowed})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"


# ── Tool 3: Reverse text ──────────────────
@mcp.tool()
def reverse_text(text: str) -> str:
    """Reverses any given text."""
    return f"Original : {text}\nReversed : {text[::-1]}"


# ── Tool 4: Word counter ──────────────────
@mcp.tool()
def count_words(text: str) -> str:
    """Counts words, characters, and sentences in the given text."""
    words      = len(text.split())
    characters = len(text)
    sentences  = text.count('.') + text.count('!') + text.count('?')
    return (
        f"Words      : {words}\n"
        f"Characters : {characters}\n"
        f"Sentences  : {sentences}"
    )


# ── Tool 5: Random number generator ──────
@mcp.tool()
def random_number(min_val: int = 1, max_val: int = 100) -> str:
    """Generate a random number between min_val and max_val."""
    number = random.randint(min_val, max_val)
    return f"Random number between {min_val} and {max_val}: {number}"


# ── Tool 6: Temperature converter ────────
@mcp.tool()
def convert_temperature(value: float, from_unit: str) -> str:
    """
    Convert temperature between Celsius, Fahrenheit, and Kelvin.
    from_unit must be: 'C', 'F', or 'K'
    """
    from_unit = from_unit.upper()
    if from_unit == "C":
        f = (value * 9 / 5) + 32
        k = value + 273.15
        return f"{value}°C  →  {f:.2f}°F  |  {k:.2f}K"
    elif from_unit == "F":
        c = (value - 32) * 5 / 9
        k = c + 273.15
        return f"{value}°F  →  {c:.2f}°C  |  {k:.2f}K"
    elif from_unit == "K":
        c = value - 273.15
        f = (c * 9 / 5) + 32
        return f"{value}K  →  {c:.2f}°C  |  {f:.2f}°F"
    else:
        return "Invalid unit. Use 'C', 'F', or 'K'."


# ── Tool 7: Async Email Sender ───────────
def is_valid_email(email: str) -> bool:
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(pattern, email) is not None

@mcp.tool()
def email_tool(
    to: Union[str, List[str]],
    subject: str,
    message: str,
    max_retries: int = 3,
    confirm: bool = False
) -> Dict:
    """Send email to single or multiple recipients (string OR list supported). Shows template and asks for confirmation before sending."""

    # 🔥 Convert string → list automatically
    if isinstance(to, str):
        to = [email.strip() for email in to.split(",") if email.strip()]

    # Validate list
    if not to or not isinstance(to, list):
        return {"success": False, "error": "Recipient list is required."}

    # Validate emails
    invalid_emails = [email for email in to if not is_valid_email(email)]
    if invalid_emails:
        logging.error(f"Invalid emails: {invalid_emails}")
        return {"success": False, "error": f"Invalid emails: {invalid_emails}"}

    # Auto subject/message
    if not subject or not subject.strip():
        subject = "[MCP Agent] No Subject Provided"

    if not message or not message.strip():
        message = "This is an auto-generated message from MCP Agent."

    # SMTP config
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        logging.error("Missing SMTP credentials.")
        return {"success": False, "error": "Missing SMTP credentials."}

    # Create message
    html_template = f"""
    <html>
        <body style='font-family: Arial; background:#f9f9f9;'>
            <div style='background:#fff;padding:20px;border-radius:8px;'>
                <h2>{subject}</h2>
                <p>{message}</p>
                <hr>
                <small>Sent by MCP Agent | {smtp_user}</small>
            </div>
        </body>
    </html>
    """

    # Show template and ask for confirmation if not confirmed
    if not confirm:
        return {
            "success": False,
            "preview": {
                "to": to,
                "subject": subject,
                "message": message,
                "html": html_template
            },
            "info": "Preview above. Set confirm=True to actually send the email."
        }

    # Actually send email
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_user
    msg["To"] = smtp_user
    msg["Bcc"] = ", ".join(to)
    msg["Subject"] = subject
    msg.attach(MIMEText(message, "plain"))
    msg.attach(MIMEText(html_template, "html"))

    attempt = 0
    while attempt < max_retries:
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, to, msg.as_string())

            logging.info(f"Email sent to {len(to)} recipients")
            return {"success": True, "message": f"Email sent to {len(to)} recipients"}

        except Exception as e:
            logging.error(f"Attempt {attempt+1} failed: {e}")
            attempt += 1
            sleep(2)

    return {"success": False, "error": "Failed after retries"}

# ───────────────────────────────────────────
#  Start the server (stdio = Claude Desktop)
# ───────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")