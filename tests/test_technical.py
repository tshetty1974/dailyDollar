import asyncio

from agents.technical import technical_agent, market_tool


async def main():

    query = """
    Analyse NVIDIA's recent market performance.

    Look at the current price and recent historical
    price trend. Give me a concise technical analysis.
    """

    print("\n>>> STARTING TECHNICAL ANALYSIS\n")

    async with market_tool:

        response = await technical_agent.run(
            query,
            tools=[market_tool],
        )

    print("=" * 60)
    print("TECHNICAL ANALYSIS")
    print("=" * 60)

    print(response.text)

    print("\n>>> FINISHED TECHNICAL ANALYSIS")


if __name__ == "__main__":
    asyncio.run(main())