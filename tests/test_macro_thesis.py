import asyncio

from agents.macro_thesis import macro_thesis_agent


async def main():

    query = """
    Analyze NVIDIA's long-term investment thesis.

    Focus on the AI semiconductor industry, structural demand
    for accelerated computing, competitive positioning,
    relevant macro factors, and the major assumptions that
    must hold for the long-term thesis to remain strong.
    """

    print("\n>>> STARTING MACRO / THESIS\n")

    response = await macro_thesis_agent.run(query)

    print("=" * 60)
    print("MACRO / THESIS")
    print("=" * 60)

    print(response)

    print("\n>>> FINISHED MACRO / THESIS")


if __name__ == "__main__":
    asyncio.run(main())