"""
Test 4 — the full pipeline end to end.

This is the expensive one: a complete five-analyst Magentic run per
candidate, plus one synthesis call. Start with a single ticker.

To test multi-stock allocation later, add "AMD" to tickers below. That
roughly doubles the cost and runtime.

Run:  PYTHONPATH=src python3 tests/test_orchestration.py
"""

import asyncio

from observability import print_report, setup_observability


# Tracing is enabled BEFORE the agent modules are imported, on purpose.
#
# configure_otel_providers() installs the global tracer provider. Any
# module that grabs a tracer at import time would otherwise capture the
# default no-op one and never emit a span. Imports below this line are
# therefore deliberately out of the usual position.
#
# This replaces the earlier httpx logging, which could never have shown
# the Gemini calls: google-genai uses aiohttp for async requests, so the
# calls we most wanted to time were invisible to it. Instrumenting the
# framework catches every agent, tool call and workflow regardless of
# transport.
setup_observability(live=True)

from models import Horizon, InvestmentRequest, RiskAppetite  # noqa: E402
from orchestration.investment_orchestrator import (  # noqa: E402
    run_investment_research,
)


async def main():

    request = InvestmentRequest(
        tickers=["HYPG"],
        amount=50_000,
        risk_appetite=RiskAppetite.MODERATE,
        horizon=Horizon.LONG,
        constraints=["No more than 40% in a single position"],
    )

    print("=" * 70)
    print("ORCHESTRATION TEST")
    print("=" * 70)
    print(request.objective_brief())

    try:
        recommendation = await run_investment_research(request)

    finally:
        # Printed even on failure: when a run dies or is interrupted,
        # the trace up to that point is exactly what you want to see.
        print_report()

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
