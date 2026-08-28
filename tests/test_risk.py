import asyncio

from agents.risk import risk_agent


async def main():

    query = """
    Analyze the key risks to investing in NVIDIA (NVDA).

    Act as a skeptical investment analyst.

    Focus on what could cause the NVIDIA investment thesis
    to fail, the assumptions behind the bullish case,
    competitive and geopolitical risks, valuation risks,
    and plausible downside scenarios.
    """

    print("\n>>> STARTING RISK ANALYSIS\n")

    response = await risk_agent.run(query)

    print("=" * 60)
    print("RISK ANALYSIS")
    print("=" * 60)

    print(response)

    print("\n>>> FINISHED RISK ANALYSIS")


if __name__ == "__main__":
    asyncio.run(main())