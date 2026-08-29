"""
Test 5 — the synthesis agent alone, on canned findings.

The orchestration is the expensive part of the pipeline, and it already
works. This exercises only the final step: can the synthesis agent turn
findings into a valid, filled-in recommendation form?

Costs one model call rather than a full five-analyst run, so use this
for iterating on the synthesis prompt or schema.

Run:  PYTHONPATH=src python3 tests/test_synthesis.py
"""

import asyncio

from models import Horizon, InvestmentRequest, RiskAppetite
from orchestration.investment_orchestrator import synthesise


# Stand-ins for what the real analysts produce. Deliberately contains
# concrete figures and filing references, so we can check whether the
# synthesis agent cites its sources rather than paraphrasing.
CANNED_FINDINGS = {
    "NVDA": {
        "Fundamentals Analyst": [
            "### Financial Health\n"
            "- Debt securities maturing within one year total $20,427M, "
            "and $19,093M in 1-5 years, for $39,520M total "
            "(10-K 2026-02-25, Item 15).\n"
            "- Liquidity is strong; short maturities dominate.\n"
            "### Fundamental Risks\n"
            "- Extended customer payment terms may affect collection "
            "(10-K 2026-02-25, Item 1A).\n"
            "- Operating expense growth may lag revenue growth, creating "
            "margin volatility (10-K 2026-02-25, Item 1A)."
        ],
        "Technical Analyst": [
            "### Price & Trend\n"
            "- Latest close $227.98, up 8.74% on the session "
            "(MCP get_stock_price).\n"
            "- Trading above the 50-day ($208.16) and 200-day ($195.57) "
            "moving averages (MCP get_technical_indicators).\n"
            "### Volatility & Drawdown\n"
            "- Annualised volatility 37.88%; max drawdown -20.21% over "
            "the last year (MCP get_technical_indicators).\n"
            "- Period range $164.98 to $235.47."
        ],
        "News & Sentiment Analyst": [
            "- Sentiment is broadly positive following recent AI "
            "infrastructure announcements.\n"
            "- Notable insider selling reported (~$410M), which some "
            "commentators read as a caution signal."
        ],
        "Macro & Investment Thesis Analyst": [
            "- Structural tailwind from sustained data-centre capex.\n"
            "- Competitive moat rests on the CUDA software ecosystem.\n"
            "- Headwind: export controls limit addressable market in "
            "some regions."
        ],
        "Risk Analyst": [
            "- Customer concentration is the single largest "
            "vulnerability; a handful of hyperscalers drive demand.\n"
            "- Valuation assumes capex persists; any digestion phase "
            "would compress both growth and the multiple.\n"
            "- 37.88% annualised volatility is high for an investor "
            "with only moderate risk appetite."
        ],
    }
}


async def main():

    request = InvestmentRequest(
        tickers=["NVDA"],
        amount=50_000,
        risk_appetite=RiskAppetite.MODERATE,
        horizon=Horizon.LONG,
        constraints=["No more than 40% in a single position"],
    )

    recommendation = await synthesise(request, CANNED_FINDINGS)

    if recommendation is None:
        print("\nFAILED: the form did not come back filled in.")
        return

    print("\n" + recommendation.render(request))

    print("\n" + "=" * 70)
    print("CHECKS")
    print("=" * 70)

    stock = recommendation.stocks[0]

    print("covers NVDA:", stock.ticker == "NVDA")
    print("allocations balance to 100%:", recommendation.is_balanced())
    print("respects the 40% cap:", stock.allocation_percent <= 40)
    print("cites at least one source:", bool(stock.evidence))
    print(
        "every evidence item names a source:",
        all(e.source for e in stock.evidence),
    )
    print("states what the debate changed:", bool(stock.debate_resolution))


if __name__ == "__main__":
    asyncio.run(main())
