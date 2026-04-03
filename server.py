from mcp.server.fastmcp import FastMCP
from datetime import datetime
import random

# ─────────────────────────────────────────
#  Create the MCP Server
# ─────────────────────────────────────────
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


# ─────────────────────────────────────────
#  Start the server (stdio = Claude Desktop)
# ─────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
