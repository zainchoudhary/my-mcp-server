import json
import requests
from groq import Groq
from dotenv import load_dotenv
import os
from rich.console import Console
from rich.markdown import Markdown
import time

load_dotenv()
console = Console()

# ─────────────────────────────
# 🔑 Setup Groq
# ─────────────────────────────
groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    console.print("[bold red]❌ GROQ_API_KEY missing in .env[/bold red]")
    exit()

client = Groq(api_key=groq_api_key)
MODEL = "llama-3.3-70b-versatile"

# ─────────────────────────────
# 🌐 SERVER CONFIG
# ─────────────────────────────
SERVER_URL = "http://127.0.0.1:8000"
MAX_RETRIES = 5
RETRY_DELAY = 1

def fetch_tools():
    """Fetch available tools from the server with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(f"{SERVER_URL}/tools", timeout=5)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.ConnectionError:
            if attempt < MAX_RETRIES - 1:
                console.print(f"[yellow]Retrying connection... ({attempt + 1}/{MAX_RETRIES})[/yellow]")
                time.sleep(RETRY_DELAY)
            else:
                console.print(f"[bold red]❌ Could not connect to server at {SERVER_URL}[/bold red]")
                console.print("[bold yellow]Make sure to run: python server.py[/bold yellow]")
                exit()
    return []

# ─────────────────────────────
# 🧠 SYSTEM PROMPT
# ─────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """
You are a powerful AI agent with access to tools.

TOOLS AVAILABLE:
{tools_json}

INSTRUCTIONS:

1. Understand the user request carefully

2. If a tool is needed → return ONLY valid JSON:
{{
  "tool": "exact_tool_name",
  "arguments": {{ "param1": "value1" }}
}}

3. If no tool needed → return:
{{
  "final_answer": "clear human response"
}}

STRICT RULES:
- Response MUST be valid JSON
- Only use tools listed above
- Never invent tool names
- Match exact parameter names
- Don't explain, just return JSON
"""
# ─────────────────────────────
# 🚀 AGENT
# ─────────────────────────────
def run_agent():
    """Main agent loop - synchronous, HTTP-based."""
    # Fetch tools from server
    tools = fetch_tools()
    if not tools:
        console.print("[bold red]❌ No tools available[/bold red]")
        return
    
    tools_json_str = json.dumps(tools, indent=2)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(tools_json=tools_json_str)
    
    console.print("\n[bold green]🔥 MCP AGENT READY[/bold green]\n")
    console.print(f"[dim]Connected to: {SERVER_URL}[/dim]")
    console.print(f"[dim]Tools available: {len(tools)}[/dim]\n")
    
    conversation_history = [{"role": "system", "content": system_prompt}]
    
    while True:
        user_input = input("👤 You: ").strip()
        if user_input.lower() in ["exit", "quit"]:
            break
        
        if not user_input:
            continue
        
        conversation_history.append({"role": "user", "content": user_input})
        
        max_turns = 5
        for turn in range(max_turns):
            # Ask LLM what to do
            response = client.chat.completions.create(
                model=MODEL,
                messages=conversation_history,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            llm_text = response.choices[0].message.content
            
            try:
                decision = json.loads(llm_text)
            except json.JSONDecodeError:
                console.print("[red]⚠️ Invalid JSON from LLM, retrying...[/red]")
                continue
            
            # Add to history
            conversation_history.append({"role": "assistant", "content": llm_text})
            
            # ───── TOOL CALL ─────
            if "tool" in decision:
                tool_name = decision["tool"]
                arguments = decision.get("arguments", {})
                
                console.print(f"🛠️  [cyan]Calling:[/cyan] {tool_name}")
                
                try:
                    # Call tool via HTTP
                    response = requests.post(
                        f"{SERVER_URL}/tools/{tool_name}",
                        json=arguments,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        result = response.json().get("result", "")
                        console.print(f"✔️  [green]Result:[/green] {result}")
                        
                        # Add to history as user message with tool result
                        conversation_history.append({
                            "role": "user",
                            "content": f"Tool '{tool_name}' executed successfully. Result: {result}"
                        })
                    else:
                        error_msg = response.json().get("detail", "Unknown error")
                        console.print(f"[red]❌ Error: {error_msg}[/red]")
                        conversation_history.append({
                            "role": "user",
                            "content": f"Tool '{tool_name}' failed with error: {error_msg}"
                        })
                        break
                
                except Exception as e:
                    console.print(f"[red]❌ Tool Error: {e}[/red]")
                    break
            
            # ───── FINAL ANSWER ─────
            elif "final_answer" in decision:
                answer = decision.get("final_answer", "No response")
                console.print("\n🤖 [bold]Agent:[/bold]")
                console.print(Markdown(answer))
                print("-" * 40)
                break
            
            else:
                console.print("[red]⚠️ Invalid response structure[/red]")
                break
        
        # Keep history manageable
        if len(conversation_history) > 12:
            conversation_history = [conversation_history[0]] + conversation_history[-11:]

# ─────────────────────────────
# ▶️ RUN
# ─────────────────────────────
if __name__ == "__main__":
    run_agent()