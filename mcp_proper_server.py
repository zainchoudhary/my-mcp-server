#!/usr/bin/env python3
"""
Proper MCP Server Implementation - Using FastMCP (Anthropic's MCP)
Following: https://spec.modelcontextprotocol.io/
"""

import sys
from datetime import datetime
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import json
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP

load_dotenv()

# ==============================================================================
# == Initialize MCP Server using FastMCP
# ==============================================================================

mcp = FastMCP("MCP-AI-Agent")

# ==============================================================================
# == Tool Definitions with MCP Decorators
# ==============================================================================

@mcp.tool()
def get_current_time() -> str:
    """Returns the current date and time."""
    return f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


@mcp.tool()
def calculate(expression: str) -> str:
    """
    Evaluate a simple math expression.
    Example: '2 + 2', '10 * 5', '100 / 4'
    """
    try:
        # Handle both module and dict forms of __builtins__
        builtins_dict = __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
        allowed = {k: v for k, v in builtins_dict.items()
                   if k in ('abs', 'round', 'min', 'max', 'sum', 'pow')}
        result = eval(expression, {"__builtins__": allowed})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"


@mcp.tool()
def reverse_text(text: str) -> str:
    """Reverses any given text."""
    return f"Original : {text}\nReversed : {text[::-1]}"


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


@mcp.tool()
def random_number(min_val: int = 1, max_val: int = 100) -> str:
    """Generate a random number between min_val and max_val."""
    number = random.randint(min_val, max_val)
    return f"Random number between {min_val} and {max_val}: {number}"


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
    return f"Unknown unit: {from_unit}"


@mcp.tool()
def email_tool(to: list, subject: str, message: str, max_retries: int = 3, confirm: bool = False) -> str:
    """Send an email using SMTP."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        return json.dumps({"success": False, "error": "Missing SMTP credentials."})

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

    if not confirm:
        return json.dumps({
            "success": False,
            "preview": {
                "to": to,
                "subject": subject,
                "message": message,
            },
            "info": "Preview above. Set confirm=True to actually send the email."
        })

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
                server.send_message(msg)
            return json.dumps({"success": True, "message": f"Email sent to {', '.join(to)}"})
        except Exception as e:
            attempt += 1
            if attempt >= max_retries:
                return json.dumps({"success": False, "error": str(e)})

    return json.dumps({"success": False, "error": "Failed after retries"})


# ==============================================================================
# == Run the MCP Server
# ==============================================================================

if __name__ == "__main__":
    print("🚀 Starting MCP Server (FastMCP)...", file=sys.stderr)
    print("📋 Tools available:", file=sys.stderr)
    print("   1. get_current_time()", file=sys.stderr)
    print("   2. calculate(expression)", file=sys.stderr)
    print("   3. reverse_text(text)", file=sys.stderr)
    print("   4. count_words(text)", file=sys.stderr)
    print("   5. random_number(min_val, max_val)", file=sys.stderr)
    print("   6. convert_temperature(value, from_unit)", file=sys.stderr)
    print("   7. email_tool(to, subject, message, max_retries, confirm)", file=sys.stderr)
    print("", file=sys.stderr)
    
    # Run on stdio transport (MCP standard)
    mcp.run(transport="stdio")
