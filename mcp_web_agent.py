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
        """Discover tools via JSON-RPC tools/list (MCP protocol) with fallback"""
        if self.tools_cache:
            return self.tools_cache
        
        # First, try JSON-RPC tools/list (proper MCP)
        response = self.send_request("tools/list")
        
        # If JSON-RPC tools/list works, use it
        if "result" in response and "tools" in response.get("result", {}):
            self.tools_cache = response["result"]["tools"]
            return self.tools_cache
        
        # Fallback: Direct import of tool schemas (for FastMCP compatibility)
        print("[INFO] JSON-RPC tools/list not available, using direct schema import", file=sys.stderr)
        from mcp_proper_server import (
            get_current_time, calculate, reverse_text, count_words,
            random_number, convert_temperature, email_tool
        )
        
        # Extract schemas from function annotations
        import inspect
        tools_list = []
        for func in [get_current_time, calculate, reverse_text, count_words, random_number, convert_temperature, email_tool]:
            sig = inspect.signature(func)
            params = {}
            required = []
            for param_name, param in sig.parameters.items():
                if param.annotation != inspect.Parameter.empty:
                    # Map Python types to JSON schema types
                    type_map = {
                        str: "string",
                        int: "integer",
                        float: "number",
                        bool: "boolean",
                        list: "array",
                    }
                    param_type = type_map.get(param.annotation, "string")
                    
                    # Special handling for email_tool parameters
                    if func.__name__ == "email_tool":
                        if param_name == "to":
                            params[param_name] = {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of recipient email addresses"
                            }
                        elif param_name == "confirm":
                            params[param_name] = {
                                "type": "boolean",
                                "description": "Confirm sending the email"
                            }
                        elif param_name == "max_retries":
                            params[param_name] = {
                                "type": "integer",
                                "description": "Number of retries (default: 3)"
                            }
                        else:
                            params[param_name] = {"type": param_type}
                    else:
                        params[param_name] = {"type": param_type}
                    
                    if param.default == inspect.Parameter.empty:
                        required.append(param_name)
            
            tools_list.append({
                "name": func.__name__,
                "description": func.__doc__ or "Tool",
                "inputSchema": {
                    "type": "object",
                    "properties": params,
                    "required": required
                }
            })
        
        self.tools_cache = tools_list
        return tools_list
    
    def call_tool(self, tool_name: str, arguments: Dict) -> str:
        """Execute tool via JSON-RPC tools/call (MCP protocol) with fallback"""
        # First, try JSON-RPC tools/call (proper MCP)
        response = self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        # If JSON-RPC works and returns a result, use it
        if "result" in response:
            result = response["result"]
            if isinstance(result, dict):
                if "text" in result:
                    return result["text"]
                if "content" in result and isinstance(result["content"], list) and len(result["content"]) > 0:
                    if isinstance(result["content"][0], dict) and "text" in result["content"][0]:
                        return result["content"][0]["text"]
            return str(result)
        
        # Fallback: Direct function import (for FastMCP compatibility)
        print(f"[INFO] JSON-RPC tools/call not available, using direct function import", file=sys.stderr)
        try:
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
            
            # Convert parameters to correct types for email_tool
            if tool_name == "email_tool":
                if "to" in arguments:
                    # Convert to to a list if it's a string
                    if isinstance(arguments["to"], str):
                        arguments["to"] = [arguments["to"]]
                if "confirm" in arguments:
                    # Convert confirm to boolean
                    if isinstance(arguments["confirm"], str):
                        arguments["confirm"] = arguments["confirm"].lower() in ("yes", "true", "1")
                if "max_retries" in arguments:
                    # Convert max_retries to int
                    if isinstance(arguments["max_retries"], str):
                        arguments["max_retries"] = int(arguments["max_retries"])
            
            result = tool_func(**arguments)
            return str(result)
            
        except Exception as e:
            error = response.get("error", {}).get("message", str(e))
            return f"Error: {error}"


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
