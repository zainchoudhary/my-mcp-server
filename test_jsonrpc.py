#!/usr/bin/env python3
"""Test JSON-RPC communication with MCP server"""
import subprocess
import json
import sys
import time

# Start the MCP server
print("Starting MCP server...")
process = subprocess.Popen(
    [sys.executable, "mcp_proper_server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)

time.sleep(1)  # Give server time to start

# Send JSON-RPC request for tools/list
print("\n📋 Testing JSON-RPC: tools/list")
request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
}

print(f"Request: {json.dumps(request)}")
json.dump(request, process.stdin)
process.stdin.write('\n')
process.stdin.flush()

# Read response
response_line = process.stdout.readline()
print(f"Raw response: {response_line}")

if response_line.strip():
    try:
        response = json.loads(response_line)
        print(f"Parsed response: {json.dumps(response, indent=2)}")
    except Exception as e:
        print(f"Error parsing: {e}")
else:
    print("No response from server!")

# Check stderr for any logs
time.sleep(0.5)
try:
    stderr_output = process.stderr.read()
    if stderr_output:
        print(f"\nServer stderr:\n{stderr_output}")
except:
    pass

# Clean up
process.terminate()
process.wait()
print("\nTest complete!")
