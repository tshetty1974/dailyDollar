"""
Test 8 — does remembered context actually reach the model?

test_memory.py proved data survives on disk. That is only half of it:
a JSON file does not make a model smarter, because the model cannot
read your disk. This proves the last step -- memory becoming prompt
text the model can answer from.

Two questions, testing the two scopes:

  Turn 1  long-term  -- answerable only from the stored profile
  Turn 2  short-term -- says "those two", which only makes sense if the
                        session carried turn 1 forward

Costs two model calls. No orchestration.

Run:  PYTHONPATH=src python3 tests/test_memory_provider.py
"""

import asyncio
import os

from dotenv import load_dotenv

from agent_framework import Agent, AgentSession
from agent_framework.gemini import GeminiChatClient

from models import (
    EvidenceItem,
    Horizon,
    InvestmentRequest,
    PortfolioRecommendation,
    RiskAppetite,
    StockRecommendation,
    Verdict,
)
from memory.provider import UserMemoryProvider
from memory.store import load_memory, memory_path, save_memory


load_dotenv()

USER = "provider_test_user"


# ------------------------------------------------------------
# Seed a past session for this user
# ------------------------------------------------------------

path = memory_path(USER)
if path.exists():
    path.unlink()

request = InvestmentRequest(
    user_id=USER,
    tickers=["NVDA", "AMD"],
    amount=75_000,
    risk_appetite=RiskAppetite.CONSERVATIVE,
    horizon=Horizon.SHORT,
    constraints=["Nothing over 30% in one position"],
)

recommendation = PortfolioRecommendation(
    summary="Cautious exposure given a conservative, short-horizon mandate.",
    stocks=[
        StockRecommendation(
            ticker="NVDA",
            verdict=Verdict.ACCUMULATE,
            conviction=4,
            allocation_percent=30,
            thesis="Durable leader in accelerated computing.",
            assumptions=["Data-centre capex stays elevated"],
            evidence=[
                EvidenceItem(
                    claim="Strong liquidity",
                    source="10-K 2026-02-25, Item 15",
                    detail="$39,520M marketable securities",
                )
            ],
            key_risks=["Customer concentration"],
            debate_resolution="Held at 30%, the user's cap.",
        ),
        StockRecommendation(
            ticker="AMD",
            verdict=Verdict.HOLD,
            conviction=2,
            allocation_percent=10,
            thesis="Second source, but volatile.",
            assumptions=["Instinct keeps winning sockets"],
            evidence=[
                EvidenceItem(
                    claim="Very high volatility",
                    source="MCP get_technical_indicators",
                    detail="71.97% annualised",
                )
            ],
            key_risks=["Volatility clashes with a conservative mandate"],
            debate_resolution="Cut to 10% on the volatility argument.",
        ),
    ],
)

memory = load_memory(USER)
memory.remember(request, recommendation)
save_memory(memory)

print(f"Seeded a past session for '{USER}'.\n")


# ------------------------------------------------------------
# An agent that has never been told any of this
# ------------------------------------------------------------

assistant = Agent(
    client=GeminiChatClient(
        api_key=os.environ["GEMINI_API_KEY"],
        model="gemini-3.5-flash-lite",
    ),
    name="Investment Assistant",
    instructions=(
        "You are an investment research assistant. Answer the user's "
        "questions about their portfolio conversationally and concisely. "
        "Never ask the user to repeat information you already know."
    ),
    context_providers=[UserMemoryProvider(user_id=USER)],
)


async def main():

    session = AgentSession()

    # --- turn 1: long-term memory -----------------------------
    #
    # Nothing in this prompt says the amount, the risk appetite or the
    # horizon. If the answer contains them, they came from disk.

    question_one = "Remind me — how much am I investing, and what risk level did I set?"

    print("=" * 70)
    print(f"TURN 1: {question_one}")
    print("=" * 70)

    first = await assistant.run(question_one, session=session)
    answer_one = (getattr(first, "text", "") or "").lower()

    print(answer_one)

    print("\nrecalls the amount ($75,000):", "75,000" in answer_one or "75000" in answer_one)
    print("recalls the risk appetite:", "conservative" in answer_one)
    print("recalls the horizon:", "short" in answer_one)

    # --- turn 2: short-term / session memory ------------------
    #
    # "those two" is meaningless without turn 1 in context.

    question_two = "Which of those two did you back more strongly, and why?"

    print("\n" + "=" * 70)
    print(f"TURN 2: {question_two}")
    print("=" * 70)

    second = await assistant.run(question_two, session=session)
    answer_two = (getattr(second, "text", "") or "").lower()

    print(answer_two)

    print("\nresolves 'those two' to NVDA/AMD:", "nvda" in answer_two or "amd" in answer_two)
    print("recalls the stronger position:", "nvda" in answer_two)
    print(
        "cites the reason from memory:",
        "volatil" in answer_two or "conviction" in answer_two or "30" in answer_two,
    )


if __name__ == "__main__":
    asyncio.run(main())
