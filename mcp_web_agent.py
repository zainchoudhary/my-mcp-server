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
        self.initialized = False
        
        # Initialize the MCP connection immediately
        self._initialize()
        
    def _initialize(self):
        """Perform MCP initialization handshake"""
        if self.initialized:
            return
        
        try:
            init_request = {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "MCP Web Agent",
                        "version": "1.0.0"
                    }
                }
            }
            
            json.dump(init_request, self.process.stdin)
            self.process.stdin.write('\n')
            self.process.stdin.flush()
            
            response_line = self.process.stdout.readline()
            if response_line.strip():
                response = json.loads(response_line)
                if "result" in response:
                    self.initialized = True
                    print("[✅] MCP initialized successfully via JSON-RPC", file=sys.stderr)
        except Exception as e:
            print(f"[⚠️] MCP initialization failed: {e}", file=sys.stderr)
        
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
        """Discover tools via JSON-RPC tools/list (MCP protocol)"""
        if self.tools_cache:
            return self.tools_cache
        
        # Use JSON-RPC tools/list (proper MCP - after initialize)
        if self.initialized:
            response = self.send_request("tools/list")
            
            if "result" in response and "tools" in response.get("result", {}):
                self.tools_cache = response["result"]["tools"]
                print("[✅] Tools retrieved via JSON-RPC", file=sys.stderr)
                return self.tools_cache
        
        # Fallback: Direct import of tool schemas (for backup compatibility)
        print("[INFO] Using direct schema import (fallback)", file=sys.stderr)
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
        """Execute tool via JSON-RPC tools/call (MCP protocol)"""
        # First, try JSON-RPC tools/call (proper MCP - after initialize)
        if self.initialized:
            response = self.send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
            
            # Extract result from MCP response format
            if "result" in response:
                result = response["result"]
                
                # MCP returns content in different formats
                if isinstance(result, dict):
                    # Format 1: {"content": [...], "isError": false}
                    if "content" in result and isinstance(result["content"], list):
                        for item in result["content"]:
                            if isinstance(item, dict) and item.get("type") == "text":
                                print("[✅] Tool executed via JSON-RPC", file=sys.stderr)
                                return item.get("text", "")
                    
                    # Format 2: {"result": "..."}
                    if "result" in result:
                        print("[✅] Tool executed via JSON-RPC", file=sys.stderr)
                        return str(result["result"])
                    
                    # Format 3: {"structuredContent": {"result": "..."}}
                    if "structuredContent" in result and "result" in result["structuredContent"]:
                        print("[✅] Tool executed via JSON-RPC", file=sys.stderr)
                        return str(result["structuredContent"]["result"])
                
                # Fallback: return as string
                print("[✅] Tool executed via JSON-RPC", file=sys.stderr)
                return str(result)
        
        # Fallback: Direct function import (for backup compatibility)
        print(f"[INFO] Using direct function import (fallback)", file=sys.stderr)
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
                    if isinstance(arguments["to"], str):
                        arguments["to"] = [arguments["to"]]
                if "confirm" in arguments:
                    if isinstance(arguments["confirm"], str):
                        arguments["confirm"] = arguments["confirm"].lower() in ("yes", "true", "1")
                if "max_retries" in arguments:
                    if isinstance(arguments["max_retries"], str):
                        arguments["max_retries"] = int(arguments["max_retries"])
            
            result = tool_func(**arguments)
            return str(result)
            
        except Exception as e:
            error = response.get("error", {}).get("message", str(e)) if isinstance(response, dict) else str(e)
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
    connected_tools = request.get("connected_tools", [])
    
    if not user_message:
        raise HTTPException(status_code=400, detail="Message required")
    
    try:
        # Add to history
        chat_history.append({"role": "user", "content": user_message})
        
        # Get tools and build prompt
        all_tools = mcp_client.get_tools()
        
        # Filter tools - ONLY use connected tools if any are connected
        if connected_tools:
            tools = [t for t in all_tools if t["name"] in connected_tools]
            available_tool_names = ", ".join([t.replace("_", " ").title() for t in connected_tools])
            mandatory_note = f"\n🔒 MANDATORY RESTRICTION: You MUST ONLY use these tools: {available_tool_names}\nDo NOT use any other tools.\nIf the user query doesn't match any of these tools, say so.\n"
        else:
            # If no tools connected, show all tools but with a note
            tools = all_tools
            mandatory_note = "\n⚠️ No tools connected yet. All tools available.\n"
        
        tools_json = json.dumps([
            {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["inputSchema"]
            }
            for tool in tools
        ], indent=2)
        
        system_prompt = SYSTEM_PROMPT.format(tools_json=tools_json) + mandatory_note
        
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

            # Block ALL tool execution if no tools are connected

            if not connected_tools:
                result["tool_call"] = {
                    "tool": tool_name,
                    "arguments": arguments
                }
                result["tool_result"] = f"❌ No tools are connected. Please connect a tool first."
                result["final_answer"] = f"You tried to use the '{tool_name}' tool, but no tools are currently connected. Please connect a tool first."
                chat_history.append({"role": "assistant", "content": llm_response})
                chat_history.append({"role": "user", "content": result["tool_result"]})
                # Do NOT call LLM again for a fallback answer
                return result

            # Enforce: Only allow execution if tool is in connected_tools
            if tool_name not in connected_tools:
                result["tool_call"] = {
                    "tool": tool_name,
                    "arguments": arguments
                }
                result["tool_result"] = f"❌ Tool '{tool_name}' is not connected. Only these tools are allowed: {', '.join(connected_tools)}."
                result["final_answer"] = f"You tried to use the '{tool_name}' tool, but it is not currently connected. Please connect it first."
                chat_history.append({"role": "assistant", "content": llm_response})
                chat_history.append({"role": "user", "content": result["tool_result"]})
                # Do NOT call LLM again for a fallback answer
                return result

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
            # STRICTEST ENFORCEMENT: If any tools are connected, only allow answers if the query matches a keyword for a connected tool. Otherwise, block all answers.
            user_message_lower = user_message.lower().strip()
            tool_keywords = {
                'get_current_time': ['what time', 'what date', 'current time', 'current date', 'what is the time'],
                'calculate': ['calculate', 'compute', '+', '-', '*', '/', 'add', 'subtract', 'multiply', 'divide', 'sum', 'total', 'equals'],
                'reverse_text': ['reverse', 'reversed'],
                'count_words': ['count words', 'word count', 'how many words'],
                'random_number': ['random', 'random number'],
                'convert_temperature': ['temperature', 'celsius', 'fahrenheit', 'convert'],
                'email_tool': ['send email', 'send mail', 'email to']
            }
            import re
            if connected_tools:
                # Only allow answer if query matches a keyword for a connected tool
                matched_connected = False
                for tool in connected_tools:
                    keywords = tool_keywords.get(tool, [])
                    for keyword in keywords:
                        regex = re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)
                        if regex.search(user_message_lower):
                            matched_connected = True
                            break
                    if matched_connected:
                        break
                if not matched_connected:
                    result["final_answer"] = "❌ The requested tool is not connected. Please connect the required tool first."
                    chat_history.append({"role": "assistant", "content": result["final_answer"]})
                    return result
            else:
                # If no tools are connected, allow answer (all tools available)
                pass
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
