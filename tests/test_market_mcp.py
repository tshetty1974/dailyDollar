"""
Test 1 — the MCP market server on its own. No LLM, no cost.

Verifies:
  * the server boots under the current interpreter
  * all three tools are exposed over MCP
  * get_technical_indicators returns clean numbers (no NaN)

Run:  PYTHONPATH=src python3 tests/test_market_mcp.py
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "mcp"
    / "market_server.py"
)


def unwrap(result):
    """Pull the payload out of an MCP tool result."""

    structured = getattr(result, "structuredContent", None)

    if structured:

        # FastMCP wraps non-dict returns under a "result" key.
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]

        return structured

    for block in getattr(result, "content", None) or []:

        text = getattr(block, "text", None)

        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text

    return None


async def main():

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
    )

    async with stdio_client(server_params) as (read, write):

        async with ClientSession(read, write) as session:

            await session.initialize()

            # --- tool discovery -------------------------------------
            tools = await session.list_tools()

            names = sorted(tool.name for tool in tools.tools)

            expected = [
                "get_historical_prices",
                "get_stock_price",
                "get_technical_indicators",
            ]

            print("TOOLS EXPOSED:", names)
            print("ALL THREE PRESENT:", names == expected)

            # --- latest quote ---------------------------------------
            price = unwrap(
                await session.call_tool(
                    "get_stock_price",
                    {"ticker": "NVDA"},
                )
            )

            print("\nget_stock_price ->")
            print(json.dumps(price, indent=2))

            # --- computed indicators --------------------------------
            indicators = unwrap(
                await session.call_tool(
                    "get_technical_indicators",
                    {
                        "ticker": "NVDA",
                        "period": "1y",
                    },
                )
            )

            print("\nget_technical_indicators ->")
            print(json.dumps(indicators, indent=2))

            # NaN is not valid JSON, so its presence here means an
            # incomplete trading session leaked into the numbers.
            blob = json.dumps([price, indicators])

            print("\nNaN PRESENT (must be False):", "NaN" in blob)


if __name__ == "__main__":
    asyncio.run(main())
