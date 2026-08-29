"""
Test 3 — the input/output contracts. No LLM, no network, no cost.

Checks that the schema accepts a well-formed portfolio, fills in cash
correctly, and rejects the malformed output we most fear from a model.

Run:  PYTHONPATH=src python3 tests/test_models.py
"""

from pydantic import ValidationError

from models import (
    EvidenceItem,
    Horizon,
    InvestmentRequest,
    PortfolioRecommendation,
    RiskAppetite,
    StockRecommendation,
    Verdict,
)


def check(label, condition):
    print(f"{'PASS' if condition else 'FAIL'}  {label}")


# ------------------------------------------------------------
# 1. Input contract
# ------------------------------------------------------------

request = InvestmentRequest(
    tickers=["nvda", "AMD", "nvda"],
    amount=50_000,
    risk_appetite=RiskAppetite.MODERATE,
    horizon=Horizon.LONG,
    constraints=["No more than 40% in a single position"],
)

print("=" * 60)
print("OBJECTIVE BRIEF (this is what every agent will see)")
print("=" * 60)
print(request.objective_brief())
print()

check("tickers uppercased and de-duplicated", request.tickers == ["NVDA", "AMD"])
check("user_id defaults", request.user_id == "default")


# ------------------------------------------------------------
# 2. Output contract
# ------------------------------------------------------------

portfolio = PortfolioRecommendation(
    summary="Balanced exposure to AI infrastructure with a cash buffer.",
    stocks=[
        StockRecommendation(
            ticker="NVDA",
            verdict=Verdict.BUY,
            conviction=4,
            allocation_percent=60,
            thesis="Dominant position in AI accelerators with pricing power.",
            assumptions=["Data-centre capex remains elevated through 2027"],
            evidence=[
                EvidenceItem(
                    claim="Trades above both its 50d and 200d moving averages",
                    source="MCP get_technical_indicators",
                    detail="close 227.98 vs sma_50 208.16, sma_200 195.57",
                )
            ],
            key_risks=["Customer concentration", "Export-control exposure"],
            debate_resolution=(
                "Bear case on concentration cut allocation from 75% to 60%."
            ),
        ),
        StockRecommendation(
            ticker="AMD",
            verdict=Verdict.ACCUMULATE,
            conviction=3,
            allocation_percent=25,
            thesis="Credible second source, earlier in its margin ramp.",
            assumptions=["MI-series wins continue to convert"],
            evidence=[
                EvidenceItem(
                    claim="Gross margin expanding year over year",
                    source="10-K 2026-02-04, Item 7",
                    detail="see MD&A margin discussion",
                )
            ],
            key_risks=["Execution risk against a stronger incumbent"],
            debate_resolution="Survived unchanged; bull and bear agreed.",
        ),
    ],
)

print("=" * 60)
print("RENDERED PORTFOLIO")
print("=" * 60)
print(portfolio.render(request))
print()

check("cash auto-filled to remainder", portfolio.cash_percent == 15.0)
check("total allocated is 100", portfolio.total_allocated == 100.0)
check("portfolio reports balanced", portfolio.is_balanced())
check(
    "dollar conversion correct",
    portfolio.stocks[0].cash_amount(request.amount) == 30_000.00,
)


# ------------------------------------------------------------
# 3. The malformed output we expect a model to produce
# ------------------------------------------------------------

def rejects(label, build):
    try:
        build()
        check(label, False)
    except ValidationError:
        check(label, True)


rejects(
    "rejects a recommendation with no evidence",
    lambda: StockRecommendation(
        ticker="NVDA",
        verdict=Verdict.BUY,
        conviction=4,
        allocation_percent=50,
        thesis="Looks good.",
        assumptions=["x"],
        evidence=[],
        key_risks=["y"],
        debate_resolution="none",
    ),
)

rejects(
    "rejects conviction outside 1-5",
    lambda: StockRecommendation(
        ticker="NVDA",
        verdict=Verdict.BUY,
        conviction=9,
        allocation_percent=50,
        thesis="Looks good.",
        assumptions=["x"],
        evidence=[
            EvidenceItem(claim="c", source="s", detail="d")
        ],
        key_risks=["y"],
        debate_resolution="none",
    ),
)

rejects(
    "rejects allocation over 100%",
    lambda: StockRecommendation(
        ticker="NVDA",
        verdict=Verdict.BUY,
        conviction=4,
        allocation_percent=140,
        thesis="Looks good.",
        assumptions=["x"],
        evidence=[
            EvidenceItem(claim="c", source="s", detail="d")
        ],
        key_risks=["y"],
        debate_resolution="none",
    ),
)

rejects(
    "rejects an empty ticker list",
    lambda: InvestmentRequest(
        tickers=[],
        amount=1000,
        risk_appetite=RiskAppetite.MODERATE,
        horizon=Horizon.LONG,
    ),
)

print("\nAll checks above should read PASS.")
