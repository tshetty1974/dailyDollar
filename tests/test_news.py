import asyncio

from agents.news import news_agent


async def main():

    ticker = "NVDA"

    print("\n>>> STARTING NEWS & SENTIMENT\n")

    response = await news_agent.run(
        f"Analyse {ticker} from your assigned perspective."
    )

    print("\n" + "=" * 60)
    print("NEWS & SENTIMENT")
    print("=" * 60)
    print(response)

    print("\n>>> FINISHED NEWS & SENTIMENT")


if __name__ == "__main__":
    asyncio.run(main())