import asyncio
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():

    server_path = (
        Path(__file__).parent / "market_server.py"
    )

    server_params = StdioServerParameters(
        command="python3",
        args=[str(server_path)],
    )

    async with stdio_client(server_params) as (
        read,
        write,
    ):

        async with ClientSession(
            read,
            write,
        ) as session:

            # Initialize the MCP connection.
            await session.initialize()

            # Discover available tools.
            tools = await session.list_tools()

            print("=" * 60)
            print("AVAILABLE MCP TOOLS")
            print("=" * 60)

            for tool in tools.tools:
                print(
                    f"\n{tool.name}"
                )
                print(
                    tool.description
                )

            # -----------------------------------------
            # Test get_stock_price
            # -----------------------------------------

            print("\n" + "=" * 60)
            print("TEST: get_stock_price")
            print("=" * 60)

            result = await session.call_tool(
                "get_stock_price",
                {
                    "ticker": "NVDA"
                },
            )

            print(result)

            # -----------------------------------------
            # Test get_historical_prices
            # -----------------------------------------

            print("\n" + "=" * 60)
            print("TEST: get_historical_prices")
            print("=" * 60)

            result = await session.call_tool(
                "get_historical_prices",
                {
                    "ticker": "NVDA",
                    "period": "1mo",
                },
            )

            print(result)


if __name__ == "__main__":
    asyncio.run(main())