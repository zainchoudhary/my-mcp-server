#!/usr/bin/env python3
"""
MCP Agent - Connects to MCP Server and uses tools intelligently
Works like Claude Desktop but with the LLM integrated
"""

import json
import sys
import subprocess
import asyncio
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import os

from groq import Groq

load_dotenv()

# ==============================================================================
# == MCP Client (Connects to MCP Server)
# ==============================================================================

class MCPClient:
    def __init__(self, server_script: str = "mcp_proper_server.py"):
        """Initialize and start the MCP server process"""
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
        
    def send_request(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Send a JSON-RPC request to the MCP server"""
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
            
            # Read response
            response_line = self.process.stdout.readline()
            if not response_line:
                return {"error": "No response from MCP server"}
            
            return json.loads(response_line)
        except Exception as e:
            return {"error": str(e)}
    
    def get_tools(self) -> List[Dict]:
        """Get list of available tools - hardcoded based on mcp_proper_server.py"""
        if self.tools_cache is not None:
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
    
    def close(self):
        """Close the MCP server process"""
        self.process.terminate()
        self.process.wait()


# ==============================================================================
# == MCP Agent (LLM + MCP Integration)
# ==============================================================================

class MCPAgent:
    def __init__(self, mcp_client: MCPClient):
        """Initialize the agent with MCP client"""
        self.mcp_client = mcp_client
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_client = Groq(api_key=self.groq_api_key) if self.groq_api_key else None
        self.conversation_history = []
        self.model = "llama-3.3-70b-versatile"
        
        if not self.groq_client:
            print("⚠️  Warning: GROQ_API_KEY not set. Agent will not work.", file=sys.stderr)
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt with available tools"""
        tools = self.mcp_client.get_tools()
        tools_description = "\n".join([
            f"- {tool['name']}: {tool['description']}"
            for tool in tools
        ])
        
        tools_json = json.dumps([
            {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["inputSchema"]
            }
            for tool in tools
        ], indent=2)
        
        return f"""You are a helpful AI assistant with access to MCP tools.

Available tools:
{tools_description}

Tool schemas for reference:
{tools_json}

When the user asks you to do something:
1. Analyze if you need to use any tools
2. If you need to use a tool, respond ONLY with valid JSON:
   {{"tool": "tool_name", "arguments": {{"param1": "value1", "param2": "value2"}}}}
3. If no tool is needed or after getting tool results, respond with:
   {{"final_answer": "Your response"}}

IMPORTANT: Always respond with valid JSON only. No other text."""

    def chat(self, user_message: str) -> Dict[str, Any]:
        """Process a user message and interact with tools"""
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Build messages for LLM
        system_prompt = self._build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}] + self.conversation_history
        
        result = {
            "user_message": user_message,
            "tool_call": None,
            "tool_result": None,
            "final_answer": None
        }
        
        try:
            # Call LLM
            response = self.groq_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            llm_response = response.choices[0].message.content
            
            try:
                llm_decision = json.loads(llm_response)
            except json.JSONDecodeError:
                return {
                    **result,
                    "final_answer": "I had trouble processing that. Please try again.",
                    "error": "JSON parse error"
                }
            
            # Handle tool call
            if "tool" in llm_decision:
                tool_name = llm_decision["tool"]
                arguments = llm_decision.get("arguments", {})
                
                result["tool_call"] = {
                    "name": tool_name,
                    "arguments": arguments
                }
                
                # Execute tool
                print(f"🔧 Calling tool: {tool_name}", file=sys.stderr)
                tool_result = self.mcp_client.call_tool(tool_name, arguments)
                result["tool_result"] = tool_result
                
                # Add to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": llm_response
                })
                self.conversation_history.append({
                    "role": "user",
                    "content": f"Tool result: {tool_result}"
                })
                
                # Call LLM again to generate final answer
                messages = [{"role": "system", "content": system_prompt}] + self.conversation_history
                
                response2 = self.groq_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                
                final_response = response2.choices[0].message.content
                try:
                    final_decision = json.loads(final_response)
                    if "final_answer" in final_decision:
                        result["final_answer"] = final_decision["final_answer"]
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": final_response
                        })
                except json.JSONDecodeError:
                    result["final_answer"] = "Tool executed successfully."
            
            # Handle direct answer (no tool needed)
            elif "final_answer" in llm_decision:
                result["final_answer"] = llm_decision["final_answer"]
                self.conversation_history.append({
                    "role": "assistant",
                    "content": llm_response
                })
            
            # Trim history to keep it manageable
            if len(self.conversation_history) > 30:
                self.conversation_history = self.conversation_history[-30:]
        
        except Exception as e:
            result["error"] = str(e)
            result["final_answer"] = f"Error: {str(e)}"
        
        return result
    
    def close(self):
        """Close the agent"""
        self.mcp_client.close()


# ==============================================================================
# == Interactive Chat Interface
# ==============================================================================

def main():
    print("🚀 Starting MCP Agent...", file=sys.stderr)
    
    # Initialize MCP client
    mcp_client = MCPClient("mcp_proper_server.py")
    
    # Wait a moment for server to start
    import time
    time.sleep(0.5)
    
    # Initialize agent
    agent = MCPAgent(mcp_client)
    
    print("📋 Available tools:", file=sys.stderr)
    for tool in mcp_client.get_tools():
        print(f"   • {tool['name']}: {tool['description']}", file=sys.stderr)
    print("", file=sys.stderr)
    
    # Interactive chat loop
    print("🤖 MCP Agent Ready! Type 'exit' to quit.", file=sys.stderr)
    print("-" * 60, file=sys.stderr)
    
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ["exit", "quit", "bye"]:
                print("👋 Goodbye!", file=sys.stderr)
                break
            
            # Process message
            result = agent.chat(user_input)
            
            # Display results
            if result.get("tool_call"):
                print(f"\n🔧 Tool Called: {result['tool_call']['name']}", file=sys.stderr)
                print(f"   Arguments: {result['tool_call']['arguments']}", file=sys.stderr)
            
            if result.get("tool_result"):
                print(f"\n📊 Tool Result:", file=sys.stderr)
                print(f"{result['tool_result']}", file=sys.stderr)
            
            if result.get("final_answer"):
                print(f"\n🤖 AI: {result['final_answer']}")
            
            if result.get("error"):
                print(f"\n❌ Error: {result['error']}", file=sys.stderr)
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!", file=sys.stderr)
            break
        except Exception as e:
            print(f"❌ Error: {e}", file=sys.stderr)
    
    agent.close()


if __name__ == "__main__":
    main()
