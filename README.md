# 🐍 My Python MCP Server — Full Setup Guide

---

## 📁 Files in this folder

| File | What it does |
|------|-------------|
| `server.py` | Your MCP server with 6 tools |
| `requirements.txt` | Python packages to install |
| `claude_desktop_config_MAC.json` | Config template for macOS |
| `claude_desktop_config_WINDOWS.json` | Config template for Windows |

---

## 🚀 STEP-BY-STEP SETUP

---

### STEP 1 — Install Python packages

Open terminal / command prompt inside this folder and run:

```
pip install mcp[cli]
```

---

### STEP 2 — Find your Python path (IMPORTANT)

**On macOS / Linux — run this:**
```
which python3
```
Example output:  /usr/bin/python3

**On Windows — run this:**
```
where python
```
Example output:  C:\Python311\python.exe

Write down this path — you need it in Step 4.

---

### STEP 3 — Find your server.py full path

**On macOS / Linux — run this inside the folder:**
```
pwd
```
Then add /server.py at the end.
Example:  /Users/ahmed/my-mcp-server/server.py

**On Windows — run this inside the folder:**
```
cd
```
Then add \server.py at the end.
Example:  C:\Users\Ahmed\my-mcp-server\server.py

---

### STEP 4 — Edit the Claude Desktop config file

This config file tells Claude Desktop WHERE your MCP server is.

**On macOS**, open this file:
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**On Windows**, open this file:
```
C:\Users\YOUR_USERNAME\AppData\Roaming\Claude\claude_desktop_config.json
```

If the file does not exist, CREATE it as a new file.

Paste this inside (replace the paths with YOUR actual paths from Step 2 and 3):

**macOS:**
```json
{
  "mcpServers": {
    "my-python-mcp": {
      "command": "/usr/bin/python3",
      "args": ["/Users/ahmed/my-mcp-server/server.py"]
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "my-python-mcp": {
      "command": "C:\\Python311\\python.exe",
      "args": ["C:\\Users\\Ahmed\\my-mcp-server\\server.py"]
    }
  }
}
```

Save the file.

---

### STEP 5 — Restart Claude Desktop

Fully QUIT Claude Desktop (not just close the window):
- macOS: Right-click Claude in dock → Quit
- Windows: Right-click Claude in system tray → Quit

Then open Claude Desktop again.

---

### STEP 6 — Check if it's working

1. Open Claude Desktop
2. Click the [ + ] button near the chat input box
3. Click "Connectors"
4. You should see "My Python MCP Server" listed ✅

---

### STEP 7 — Test your tools!

Type these in Claude chat:

- "What time is it right now?"
- "Calculate 456 * 789"
- "Reverse the text: Hello World"
- "Count words in: The quick brown fox jumps over the lazy dog"
- "Give me a random number between 1 and 50"
- "Convert 100 Celsius to Fahrenheit"

---

## 🛠️ Available Tools

| Tool | What it does |
|------|-------------|
| `get_current_time` | Returns current date & time |
| `calculate` | Solves math expressions |
| `reverse_text` | Reverses any text |
| `count_words` | Counts words, characters, sentences |
| `random_number` | Generates a random number in a range |
| `convert_temperature` | Converts between C, F, and K |

---

## ❌ Common Errors

**"Server not showing in Claude"**
→ Make sure you fully quit and restarted Claude Desktop
→ Check the paths in the config file are correct

**"python not found" error**
→ Use the full python path from Step 2 (e.g. /usr/bin/python3)

**"Module not found: mcp"**
→ Run: pip install mcp[cli]

---

## 💡 How to Add More Tools

Open server.py and add a new function like this:

```python
@mcp.tool()
def my_new_tool(input_text: str) -> str:
    """Describe what this tool does."""
    return f"Result: {input_text}"
```

Then restart Claude Desktop and your new tool appears automatically!
