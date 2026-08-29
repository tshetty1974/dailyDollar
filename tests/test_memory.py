"""
Test 7 — long-term memory. No LLM, no network, no cost.

Proves the core claim of requirement 3.6: something written in one
session can be read back in another. The second half of this test
throws away the in-memory object entirely and re-reads from disk, which
is exactly what a new process does.

Run:  PYTHONPATH=src python3 tests/test_memory.py
"""

from models import (
    EvidenceItem,
    Horizon,
    InvestmentRequest,
    PortfolioRecommendation,
    RiskAppetite,
    StockRecommendation,
    Verdict,
)
from memory.store import load_memory, memory_path, save_memory


USER = "test_user"


def check(label, condition):
    print(f"{'PASS' if condition else 'FAIL'}  {label}")


request = InvestmentRequest(
    user_id=USER,
    tickers=["NVDA", "AMD"],
    amount=50_000,
    risk_appetite=RiskAppetite.MODERATE,
    horizon=Horizon.LONG,
    constraints=["No more than 40% in a single position"],
)

recommendation = PortfolioRecommendation(
    summary="Balanced AI infrastructure exposure with a cash buffer.",
    stocks=[
        StockRecommendation(
            ticker="NVDA",
            verdict=Verdict.ACCUMULATE,
            conviction=4,
            allocation_percent=35,
            thesis="Dominant in accelerated computing.",
            assumptions=["Data-centre capex stays elevated"],
            evidence=[
                EvidenceItem(
                    claim="Strong liquidity",
                    source="10-K 2026-02-25, Item 15",
                    detail="$39,520M marketable securities",
                )
            ],
            key_risks=["Customer concentration"],
            debate_resolution="Survived the debate at 35%.",
        ),
        StockRecommendation(
            ticker="AMD",
            verdict=Verdict.ACCUMULATE,
            conviction=3,
            allocation_percent=25,
            thesis="Credible second source.",
            assumptions=["Instinct accelerators keep winning sockets"],
            evidence=[
                EvidenceItem(
                    claim="High volatility",
                    source="MCP get_technical_indicators",
                    detail="71.97% annualised",
                )
            ],
            key_risks=["Execution risk against the incumbent"],
            debate_resolution="Narrowed to a #2-position claim.",
        ),
    ],
)


# ------------------------------------------------------------
# Session 1 — start empty, record an analysis, save
# ------------------------------------------------------------

# Start from a clean slate so repeated runs behave identically.
path = memory_path(USER)
if path.exists():
    path.unlink()

session_one = load_memory(USER)

check("a first-time user starts with no history", session_one.history == [])
check(
    "a first-time user has no previous objective",
    session_one.last_request is None,
)

session_one.remember(request, recommendation)
save_memory(session_one)

check("memory file was written", path.exists())


# ------------------------------------------------------------
# Session 2 — a brand new object, read from disk
# ------------------------------------------------------------
#
# Nothing is carried over in code. This object knows only what the file
# on disk tells it, which is what a restarted process sees.

session_two = load_memory(USER)

check("history survived", len(session_two.history) == 1)

check(
    "last objective survived",
    session_two.last_request is not None
    and session_two.last_request.amount == 50_000,
)

check(
    "constraints survived",
    session_two.last_request is not None
    and session_two.last_request.constraints
    == ["No more than 40% in a single position"],
)

# Each analysis keeps the parameters it was actually run under, so a
# later analysis with different settings cannot rewrite this one's
# history.
stored = session_two.history[0]

check(
    "the analysis stored its own risk appetite",
    stored.request.risk_appetite is RiskAppetite.MODERATE,
)

check(
    "the analysis stored its own horizon",
    stored.request.horizon is Horizon.LONG,
)

check(
    "the analysis stored its own amount",
    stored.request.amount == 50_000,
)

check(
    "holdings computed from allocations",
    session_two.holdings == {"NVDA": 17_500.00, "AMD": 12_500.00},
)

latest = session_two.latest()

check(
    "the recommendation itself survived, not just a summary",
    latest is not None
    and latest.recommendation.stocks[0].evidence[0].source
    == "10-K 2026-02-25, Item 15",
)


# ------------------------------------------------------------
# Session 3 — a second, completely different investment
# ------------------------------------------------------------
#
# The same person makes a small speculative punt. Their earlier cautious
# $50,000 analysis must not be retroactively rewritten as aggressive.

small_punt = InvestmentRequest(
    user_id=USER,
    tickers=["AMD"],
    amount=1_000,
    risk_appetite=RiskAppetite.AGGRESSIVE,
    horizon=Horizon.SHORT,
    constraints=[],
)

punt_recommendation = PortfolioRecommendation(
    summary="Small speculative position.",
    stocks=[
        StockRecommendation(
            ticker="AMD",
            verdict=Verdict.BUY,
            conviction=2,
            allocation_percent=100,
            thesis="High-risk momentum play with money the user can lose.",
            assumptions=["Momentum persists over the short horizon"],
            evidence=[
                EvidenceItem(
                    claim="Very high volatility",
                    source="MCP get_technical_indicators",
                    detail="71.97% annualised",
                )
            ],
            key_risks=["Could lose most of the position"],
            debate_resolution="Skeptic's warning accepted; sized as a punt.",
        )
    ],
)

session_two.remember(small_punt, punt_recommendation)
save_memory(session_two)

session_three = load_memory(USER)

check("both analyses are on record", len(session_three.history) == 2)

check(
    "the FIRST analysis kept its own moderate risk appetite",
    session_three.history[0].request.risk_appetite is RiskAppetite.MODERATE,
)

check(
    "the SECOND analysis kept its own aggressive risk appetite",
    session_three.history[1].request.risk_appetite is RiskAppetite.AGGRESSIVE,
)

check(
    "the first analysis kept its own $50,000",
    session_three.history[0].request.amount == 50_000,
)

check(
    "last_request now offers the most recent as a default",
    session_three.last_request is not None
    and session_three.last_request.amount == 1_000,
)


# ------------------------------------------------------------
# What the conversational agent will actually see
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("RECALL BRIEF — injected into the conversational agent")
print("=" * 70)
print(session_three.recall_brief())

print("\n" + "=" * 70)
print(f"Memory file: {path}")
print("Open it to see exactly what persisted.")
print("=" * 70)
