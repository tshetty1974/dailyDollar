"""
Test 4 — the full pipeline end to end.

This is the expensive one: a complete five-analyst Magentic run per
candidate, plus one synthesis call. Start with a single ticker.

To test multi-stock allocation later, add "AMD" to tickers below. That
roughly doubles the cost and runtime.

Run:  PYTHONPATH=src python3 tests/test_orchestration.py
"""

import asyncio

from models import Horizon, InvestmentRequest, RiskAppetite
from orchestration.investment_orchestrator import run_investment_research


async def main():

    request = InvestmentRequest(
        tickers=["NVDA", "AMD"],
        amount=50_000,
        risk_appetite=RiskAppetite.MODERATE,
        horizon=Horizon.LONG,
        constraints=["No more than 40% in a single position"],
    )

    print("=" * 70)
    print("ORCHESTRATION TEST")
    print("=" * 70)
    print(request.objective_brief())

    recommendation = await run_investment_research(request)

    print("\n")

    if recommendation is None:
        print("FAILED: no structured recommendation was produced.")
        return

    print(recommendation.render(request))

    # --- checks -------------------------------------------------
    print("\n" + "=" * 70)
    print("CHECKS")
    print("=" * 70)

    covered = {stock.ticker for stock in recommendation.stocks}

    print(
        "every candidate covered:",
        covered == set(request.tickers),
        f"(got {sorted(covered)})",
    )

    print("allocations balance to 100%:", recommendation.is_balanced())

    cited = all(
        stock.evidence and all(e.source for e in stock.evidence)
        for stock in recommendation.stocks
    )
    print("every stock cites at least one source:", cited)

    within_cap = all(
        stock.allocation_percent <= 40 for stock in recommendation.stocks
    )
    print("respects the 40% single-position constraint:", within_cap)


if __name__ == "__main__":
    asyncio.run(main())
