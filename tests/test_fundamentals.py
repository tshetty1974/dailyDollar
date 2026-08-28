import asyncio

from agents.fundamentals import fundamentals_agent


async def main():

    query = """
    Analyze NVIDIA (NVDA) from a fundamental financial-health perspective.

    Focus only on:
    - Revenue and earnings growth
    - Profitability and margins
    - Cash flow
    - Balance sheet strength

    Use the SEC filing search tool.

    Use the minimum number of searches necessary to retrieve
    sufficient evidence.
    """

    print("\n>>> STARTING FUNDAMENTALS\n")

    response = await fundamentals_agent.run(query)

    print("=" * 60)
    print("FUNDAMENTALS")
    print("=" * 60)

    print(response)

    print("\n>>> FINISHED FUNDAMENTALS")


if __name__ == "__main__":
    asyncio.run(main())