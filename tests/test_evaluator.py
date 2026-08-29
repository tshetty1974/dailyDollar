"""
Test 6 — does the critic actually reject a bad draft?

Real runs have scored 5/5/5 and been accepted, which means the revision
branch has never executed. That leaves requirement 3.4 built but
undemonstrated.

This feeds the evaluator a deliberately defective draft and checks that
it returns "revise" with a specific critique. Two model calls: one to
judge the bad draft, one to confirm a sound draft is still accepted.

Run:  PYTHONPATH=src python3 tests/test_evaluator.py
"""

import asyncio

from models import (
    EvaluationVerdict,
    EvidenceItem,
    Horizon,
    InvestmentRequest,
    PortfolioRecommendation,
    RiskAppetite,
    StockRecommendation,
    Verdict,
)
from orchestration.investment_orchestrator import evaluate


request = InvestmentRequest(
    tickers=["NVDA"],
    amount=50_000,
    risk_appetite=RiskAppetite.CONSERVATIVE,
    horizon=Horizon.SHORT,
    constraints=["No more than 40% in a single position"],
)


# Defective on purpose, in three separate ways:
#   1. 75% breaches the user's stated 40% cap
#   2. the evidence cites no real source
#   3. severe risks are listed, then ignored by a maximum-conviction,
#      oversized position for a conservative short-horizon investor
BAD_DRAFT = PortfolioRecommendation(
    summary="Go big on NVDA. It is the best AI stock available.",
    stocks=[
        StockRecommendation(
            ticker="NVDA",
            verdict=Verdict.BUY,
            conviction=5,
            allocation_percent=75,
            thesis="AI is the future and NVIDIA is winning.",
            assumptions=["The AI boom will continue indefinitely"],
            evidence=[
                EvidenceItem(
                    claim="NVIDIA is highly profitable",
                    source="general knowledge",
                    detail="everyone knows this",
                )
            ],
            key_risks=[
                "Extreme volatility of 37.88% annualised",
                "Severe customer concentration risk",
                "Potential for 20%+ drawdowns",
            ],
            debate_resolution="N/A",
        )
    ],
    cash_percent=25,
)


GOOD_DRAFT = PortfolioRecommendation(
    summary=(
        "A cautious 15% position in NVDA, sized down for a conservative "
        "investor with a short horizon, with the balance held in cash."
    ),
    stocks=[
        StockRecommendation(
            ticker="NVDA",
            verdict=Verdict.ACCUMULATE,
            conviction=3,
            allocation_percent=15,
            thesis=(
                "Durable position in AI accelerators, but sized small "
                "because the volatility is poorly matched to a "
                "conservative investor over a short horizon."
            ),
            assumptions=["Data-centre capex remains elevated into 2027"],
            evidence=[
                EvidenceItem(
                    claim="Liquidity is strong",
                    source="10-K 2026-02-25, Item 15",
                    detail="$39,520M in marketable debt securities",
                ),
                EvidenceItem(
                    claim="Volatility is high relative to this investor",
                    source="MCP get_technical_indicators",
                    detail="37.88% annualised, max drawdown -20.21%",
                ),
            ],
            key_risks=[
                "Customer concentration among a few hyperscalers",
                "37.88% volatility is high for a conservative mandate",
            ],
            debate_resolution=(
                "The skeptic's volatility argument cut the position from "
                "30% to 15% for this risk profile."
            ),
        )
    ],
    cash_percent=85,
)


async def main():

    print("=" * 70)
    print("CASE 1 — DEFECTIVE DRAFT (should be REVISE)")
    print("=" * 70)

    bad = await evaluate(request, BAD_DRAFT)

    if bad is None:
        print("FAILED: evaluator output could not be parsed")
        return

    print(f"\nverdict:  {bad.verdict.value}")
    print(f"critique: {bad.critique}\n")

    print("rejects the defective draft:", bad.verdict is EvaluationVerdict.REVISE)
    print(
        "critique mentions the breached cap:",
        "40" in bad.critique or "75" in bad.critique,
    )

    print("\n" + "=" * 70)
    print("CASE 2 — SOUND DRAFT (should be ACCEPT)")
    print("=" * 70)

    good = await evaluate(request, GOOD_DRAFT)

    if good is None:
        print("FAILED: evaluator output could not be parsed")
        return

    print(f"\nverdict:  {good.verdict.value}")
    print(f"critique: {good.critique}\n")

    print("accepts the sound draft:", good.verdict is EvaluationVerdict.ACCEPT)

    print(
        "\nDiscriminates between the two:",
        bad.verdict is EvaluationVerdict.REVISE
        and good.verdict is EvaluationVerdict.ACCEPT,
    )


if __name__ == "__main__":
    asyncio.run(main())
