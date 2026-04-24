#!/usr/bin/env python3
"""
MCP Web Agent - FastAPI server that connects to MCP server and provides web UI
Works like Claude Desktop but accessible via web browser
"""

import json
import subprocess
import sys
import asyncio
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import uvicorn
from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

# ==============================================================================
# == MCP Client (Communicates with MCP Server via stdio)
# ==============================================================================

class MCPClientSync:
    """Synchronous MCP client for use in FastAPI"""
    
    def __init__(self, server_script: str = "mcp_proper_server.py"):
        self.process = subprocess.Popen(
            [sys.executable, server_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        self.request_id = 0
        self.tools_cache = None
        
    def send_request(self, method: str, params: Optional[Dict] = None) -> Dict:
        """Send JSON-RPC request to MCP server"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }
        
        try:
            json.dump(request, self.process.stdin)
            self.process.stdin.write('\n')
            self.process.stdin.flush()
            
            response_line = self.process.stdout.readline()
            if not response_line:
                return {"error": "No response from MCP server"}
            
            return json.loads(response_line)
        except Exception as e:
            return {"error": str(e)}
    
    def get_tools(self):
        """Get available tools - hardcoded based on mcp_proper_server.py"""
        if self.tools_cache:
            return self.tools_cache
        
        # Hardcoded tools list - matches mcp_proper_server.py @mcp.tool() definitions
        self.tools_cache = [
            {
                "name": "get_current_time",
                "description": "Returns the current date and time.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "calculate",
                "description": "Evaluate a simple math expression. Example: '2 + 2', '10 * 5', '100 / 4'",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"}
                    },
                    "required": ["expression"]
                }
            },
            {
                "name": "reverse_text",
                "description": "Reverses any given text.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "count_words",
                "description": "Counts words, characters, and sentences in the given text.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "random_number",
                "description": "Generate a random number between min_val and max_val.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "min_val": {"type": "integer", "default": 1},
                        "max_val": {"type": "integer", "default": 100}
                    },
                    "required": []
                }
            },
            {
                "name": "convert_temperature",
                "description": "Convert temperature between Celsius, Fahrenheit, and Kelvin.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "number"},
                        "from_unit": {"type": "string", "enum": ["C", "F", "K"]}
                    },
                    "required": ["value", "from_unit"]
                }
            },
            {
                "name": "email_tool",
                "description": "Send an email using SMTP. Use list of email addresses for 'to' parameter.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "message": {"type": "string"},
                        "confirm": {"type": "boolean", "default": False}
                    },
                    "required": ["to", "subject", "message"]
                }
            }
        ]
        return self.tools_cache
    
    def call_tool(self, tool_name: str, arguments: Dict) -> str:
        """Execute a tool by directly calling the function"""
        try:
            # Import the tool functions directly
            import sys
            sys.path.insert(0, '.')
            from mcp_proper_server import (
                get_current_time, calculate, reverse_text, count_words,
                random_number, convert_temperature, email_tool
            )
            
            tools_map = {
                "get_current_time": get_current_time,
                "calculate": calculate,
                "reverse_text": reverse_text,
                "count_words": count_words,
                "random_number": random_number,
                "convert_temperature": convert_temperature,
                "email_tool": email_tool,
            }
            
            if tool_name not in tools_map:
                return f"Error: Tool '{tool_name}' not found"
            
            tool_func = tools_map[tool_name]
            result = tool_func(**arguments)
            return str(result)
            
        except Exception as e:
            return f"Error executing tool: {str(e)}"


# ==============================================================================
# == FastAPI App
# ==============================================================================

app = FastAPI(title="MCP Web Agent")

# Initialize MCP client
try:
    mcp_client = MCPClientSync("mcp_proper_server.py")
    import time
    time.sleep(0.5)
except Exception as e:
    print(f"Error starting MCP server: {e}", file=sys.stderr)
    mcp_client = None

# Initialize Groq
groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key else None

# Chat history
chat_history = []

SYSTEM_PROMPT = """You are a helpful AI assistant with access to MCP tools.

Available tools:
{tools_json}

**IMPORTANT: ONLY use tool names exactly as listed above. No aliases, no shortcuts.**

WORKFLOW:
1. Analyze the user request
2. If you need to call a tool:
   - Look up the EXACT tool name from the list above
   - Build JSON: {{"tool": "exact_tool_name", "arguments": {{param_name: param_value}}}}
   - Respond with ONLY this JSON
   - Do NOT add any explanation or extra text
3. If you don't need a tool or after getting tool result:
   - Respond with: {{"final_answer": "Your complete response"}}
   - Do NOT use tool names from other systems
   - Do NOT invent tool names

CRITICAL RULES:
- Output MUST be valid JSON only
- NEVER use generic names like 'datetime', 'email', 'random', etc.
- ONLY use tool names from the list above
- If unsure about exact parameters, ask user or make best guess with available info"""


@app.get("/")
async def root():
    """Serve the web UI"""
    return FileResponse("templates/mcp_agent.html")


@app.get("/tools")
async def list_tools():
    """List available tools from MCP server"""
    if not mcp_client:
        return {"error": "MCP server not initialized"}
    
    tools = mcp_client.get_tools()
    return {"tools": tools}


@app.post("/chat")
async def chat(request: Dict):
    """Chat endpoint - uses MCP tools via LLM"""
    global chat_history
    
    if not mcp_client or not groq_client:
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    user_message = request.get("message", "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message required")
    
    try:
        # Add to history
        chat_history.append({"role": "user", "content": user_message})
        
        # Get tools and build prompt
        tools = mcp_client.get_tools()
        tools_json = json.dumps([
            {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["inputSchema"]
            }
            for tool in tools
        ], indent=2)
        
        system_prompt = SYSTEM_PROMPT.format(tools_json=tools_json)
        
        # Call LLM
        messages = [{"role": "system", "content": system_prompt}] + chat_history
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        llm_response = response.choices[0].message.content
        
        try:
            llm_decision = json.loads(llm_response)
        except json.JSONDecodeError:
            return {
                "final_answer": "I had trouble processing that.",
                "tool_call": None,
                "tool_result": None
            }
        
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
            
            # Execute tool via MCP
            tool_result = mcp_client.call_tool(tool_name, arguments)
            result["tool_result"] = tool_result
            
            # Add to history
            chat_history.append({"role": "assistant", "content": llm_response})
            chat_history.append({"role": "user", "content": f"Tool result: {tool_result}"})
            
            # Call LLM again for final answer
            messages = [{"role": "system", "content": system_prompt}] + chat_history
            
            response2 = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            final_response = response2.choices[0].message.content
            try:
                final_decision = json.loads(final_response)
                if "final_answer" in final_decision:
                    result["final_answer"] = final_decision["final_answer"]
                    chat_history.append({"role": "assistant", "content": final_response})
            except:
                result["final_answer"] = "Tool executed successfully."
        
        # Handle direct answer
        elif "final_answer" in llm_decision:
            result["final_answer"] = llm_decision["final_answer"]
            chat_history.append({"role": "assistant", "content": llm_response})
        
        # Trim history
        if len(chat_history) > 30:
            chat_history = chat_history[-30:]
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("🚀 Starting MCP Web Agent...", file=sys.stderr)
    print(f"📋 Available at http://127.0.0.1:5001", file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=5001)
