import inspect
import requests
from datetime import datetime
import random
from dotenv import load_dotenv
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Union, List, Dict, Callable
from time import sleep
import re
import asyncio
import json

from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from groq import Groq

# Load environment variables from .env
load_dotenv()

# ==============================================================================
# == Custom Tool Registry (Replaces MCP)
# ==============================================================================

TOOL_REGISTRY = {}

def get_type_name(t):
    """Gets the JSON schema type name for a Python type."""
    if t == str:
        return "string"
    if t == int:
        return "integer"
    if t == float:
        return "number"
    if t == bool:
        return "boolean"
    if hasattr(t, '__origin__'):
        if t.__origin__ == list:
            return "array"
        if t.__origin__ == Union:
            return get_type_name(t.__args__[0])
    return "string"

def register_tool(func: Callable):
    """
    A decorator to register a function as a tool, automatically generating its
    JSON schema for the LLM.
    """
    tool_name = func.__name__
    description = func.__doc__.strip() if func.__doc__ else ""

    sig = inspect.signature(func)
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    for name, param in sig.parameters.items():
        param_type = get_type_name(param.annotation)
        parameters["properties"][name] = {
            "type": param_type,
            "description": f"Parameter '{name}'",
        }
        if param.default == inspect.Parameter.empty:
            parameters["required"].append(name)

    TOOL_REGISTRY[tool_name] = {
        "function": func,
        "schema": {
            "name": tool_name,
            "description": description,
            "parameters": parameters,
        }
    }
    return func


# ── Tool 1: Get current date & time ──────
@register_tool
def get_current_time() -> str:
    """Returns the current date and time."""
    return f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


# ── Tool 2: Calculator ────────────────────
@register_tool
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
@register_tool
def reverse_text(text: str) -> str:
    """Reverses any given text."""
    return f"Original : {text}\nReversed : {text[::-1]}"


# ── Tool 4: Word counter ──────────────────
@register_tool
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
@register_tool
def random_number(min_val: int = 1, max_val: int = 100) -> str:
    """Generate a random number between min_val and max_val."""
    number = random.randint(min_val, max_val)
    return f"Random number between {min_val} and {max_val}: {number}"


# ── Tool 6: Temperature converter ────────
@register_tool
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

@register_tool
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

# ==============================================================================
# == FastAPI Server Implementation
# ==============================================================================
# == FastAPI Server Implementation
# ==============================================================================
app = FastAPI()

# Setup Groq client
groq_api_key = os.getenv("GROQ_API_KEY")
if groq_api_key:
    groq_client = Groq(api_key=groq_api_key)
else:
    groq_client = None

GROQ_MODEL = "llama-3.3-70b-versatile"

# Conversation history per session
chat_history = []

SYSTEM_PROMPT = """You are a helpful AI assistant with access to tools.

Available tools:
{tools_json}

Instructions:
1. Understand the user's request
2. If a tool is needed, respond with ONLY valid JSON:
{{"tool": "tool_name", "arguments": {{"param": "value"}}}}

3. If no tool needed or after getting tool result, respond with:
{{"final_answer": "Your response"}}

STRICT: Always respond with valid JSON only. No other text."""

@app.get("/")
async def root():
    """Serve the web UI"""
    return FileResponse("templates/index.html")

@app.post("/chat")
async def chat(request: Dict):
    """Chat endpoint that processes user messages and calls tools"""
    global chat_history
    
    user_message = request.get("message", "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message required")
    
    if not groq_client:
        raise HTTPException(status_code=500, detail="Groq API key not configured")
    
    try:
        # Add user message to history
        chat_history.append({"role": "user", "content": user_message})
        
        # Get available tools
        tools_list = [tool["schema"] for tool in TOOL_REGISTRY.values()]
        tools_json = json.dumps(tools_list, indent=2)
        system_prompt = SYSTEM_PROMPT.format(tools_json=tools_json)
        
        # Call LLM
        messages = [{"role": "system", "content": system_prompt}] + chat_history
        
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        llm_response_text = response.choices[0].message.content
        
        try:
            llm_decision = json.loads(llm_response_text)
        except json.JSONDecodeError:
            return JSONResponse({
                "final_answer": "I had trouble processing that. Please try again."
            })
        
        result = {
            "tool_call": None,
            "tool_result": None,
            "final_answer": None
        }
        
        # Handle tool call
        if "tool" in llm_decision:
            tool_name = llm_decision["tool"]
            arguments = llm_decision.get("arguments", {})
            
            result["tool_call"] = {
                "tool": tool_name,
                "arguments": arguments
            }
            
            # Execute tool
            if tool_name in TOOL_REGISTRY:
                tool_func = TOOL_REGISTRY[tool_name]["function"]
                try:
                    tool_result = tool_func(**arguments)
                    result["tool_result"] = str(tool_result)
                    
                    # Add to history
                    chat_history.append({"role": "assistant", "content": llm_response_text})
                    chat_history.append({"role": "user", "content": f"Tool '{tool_name}' returned: {tool_result}"})
                    
                    # Call LLM again to generate final answer
                    messages = [{"role": "system", "content": system_prompt}] + chat_history
                    
                    response2 = groq_client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=messages,
                        temperature=0.1,
                        response_format={"type": "json_object"}
                    )
                    
                    final_response_text = response2.choices[0].message.content
                    final_decision = json.loads(final_response_text)
                    
                    if "final_answer" in final_decision:
                        result["final_answer"] = final_decision["final_answer"]
                        chat_history.append({"role": "assistant", "content": final_response_text})
                
                except Exception as e:
                    result["tool_result"] = f"Error: {str(e)}"
                    result["final_answer"] = f"Tool execution failed: {str(e)}"
            else:
                result["tool_result"] = f"Tool '{tool_name}' not found"
                result["final_answer"] = f"I couldn't find the tool '{tool_name}'"
        
        # Handle final answer (no tool needed)
        elif "final_answer" in llm_decision:
            result["final_answer"] = llm_decision["final_answer"]
            chat_history.append({"role": "assistant", "content": llm_response_text})
        
        # Trim chat history to keep it manageable
        if len(chat_history) > 20:
            chat_history = chat_history[-20:]
        
        return JSONResponse(result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tools")
async def get_tools():
    """Endpoint to list all available tools."""
    return JSONResponse(content=[tool["schema"] for tool in TOOL_REGISTRY.values()])

@app.post("/tools/{tool_name}")
async def execute_tool(tool_name: str, arguments: Dict = Body(...)):
    """Endpoint to execute a specific tool."""
    if tool_name not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found.")
    
    tool_info = TOOL_REGISTRY[tool_name]
    func = tool_info["function"]
    
    try:
        result = func(**arguments)
        return JSONResponse(content={"result": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing tool '{tool_name}': {str(e)}")

# ==============================================================================
# == Run the server using Uvicorn
# ==============================================================================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)