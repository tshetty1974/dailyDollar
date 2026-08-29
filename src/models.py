"""
The input and output contracts for the investment research system.

Everything the user supplies enters through InvestmentRequest, and
everything the system concludes leaves through PortfolioRecommendation.
Keeping both in one module makes the system's boundary explicit and
gives the memory layer a single shape to persist.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================
# INPUT CONTRACT
# ============================================================


class RiskAppetite(str, Enum):
    """How much drawdown the user is willing to tolerate."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class Horizon(str, Enum):
    """How long the user intends to hold."""

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


# Rendered into prompts so every agent reads the same definition of
# the user's constraints rather than inventing its own.
RISK_DESCRIPTIONS = {
    RiskAppetite.CONSERVATIVE: (
        "prioritises capital preservation; avoid high-volatility or "
        "speculative positions; prefers established cash-generative "
        "businesses"
    ),
    RiskAppetite.MODERATE: (
        "accepts moderate volatility in exchange for growth; balanced "
        "between preservation and appreciation"
    ),
    RiskAppetite.AGGRESSIVE: (
        "accepts high volatility and drawdown risk in pursuit of "
        "higher returns; tolerant of concentrated positions"
    ),
}

HORIZON_DESCRIPTIONS = {
    Horizon.SHORT: "under 1 year",
    Horizon.MEDIUM: "1 to 3 years",
    Horizon.LONG: "3 years or more",
}


# Used when the user does not state a preference.
#
# Risk defaults to the most cautious setting deliberately: assuming
# someone tolerates large losses when they have not said so is the more
# damaging of the two possible errors.
DEFAULT_RISK_APPETITE = RiskAppetite.CONSERVATIVE

DEFAULT_HORIZON = Horizon.MEDIUM


class InvestmentRequest(BaseModel):
    """
    A single research request: what to analyse, and for whom.

    This doubles as the persisted user profile. The memory layer stores
    this object directly rather than defining a parallel shape, so the
    profile and the request can never drift apart.
    """

    # Keyed by user even though the system serves one user today. This
    # costs nothing now and means multi-user is a storage concern
    # rather than a redesign.
    user_id: str = "default"

    tickers: list[str] = Field(min_length=1)

    amount: float = Field(gt=0, description="Investable cash in USD.")

    risk_appetite: RiskAppetite = DEFAULT_RISK_APPETITE

    horizon: Horizon = DEFAULT_HORIZON

    # Free-form user rules, e.g. "no more than 25% in one position".
    constraints: list[str] = Field(default_factory=list)

    @field_validator("tickers")
    @classmethod
    def normalise_tickers(cls, tickers: list[str]) -> list[str]:
        """Uppercase and de-duplicate while preserving order."""

        seen = []

        for ticker in tickers:

            symbol = ticker.upper().strip()

            if symbol and symbol not in seen:
                seen.append(symbol)

        return seen

    def objective_brief(self) -> str:
        """
        Render the objective as prompt text.

        Every agent receives the user's objective through this one
        method, so there is a single place that controls how the
        constraints are described to the model.
        """

        constraint_lines = (
            "\n".join(f"- {c}" for c in self.constraints)
            if self.constraints
            else "- None specified"
        )

        return f"""
INVESTMENT OBJECTIVE

Candidates:      {", ".join(self.tickers)}
Amount:          ${self.amount:,.2f}
Risk appetite:   {self.risk_appetite.value} -- {RISK_DESCRIPTIONS[self.risk_appetite]}
Time horizon:    {self.horizon.value} -- {HORIZON_DESCRIPTIONS[self.horizon]}

User constraints:
{constraint_lines}

Every conclusion must be justified against this objective. A position
that is attractive in isolation may still be wrong for this user's
risk appetite or horizon.
""".strip()


# ============================================================
# OUTPUT CONTRACT
# ============================================================


class Verdict(str, Enum):
    """The action being recommended for a single candidate."""

    BUY = "buy"
    ACCUMULATE = "accumulate"
    HOLD = "hold"
    AVOID = "avoid"


class EvidenceItem(BaseModel):
    """
    One factual claim tied back to where it came from.

    This is the mechanism behind requirement 3.5: a claim is only
    considered grounded if it can name its source, so the source is a
    required field rather than an optional citation.
    """

    claim: str = Field(description="The factual claim being made.")

    source: str = Field(
        description=(
            "Where it came from, e.g. '10-K 2026-02-25, Item 1A' or "
            "'MCP get_technical_indicators'."
        )
    )

    detail: str = Field(
        description="The figure or quotation that supports the claim."
    )


class StockRecommendation(BaseModel):
    """The system's conclusion on one candidate stock."""

    ticker: str

    verdict: Verdict

    conviction: int = Field(
        ge=1,
        le=5,
        description="1 = very low confidence, 5 = very high.",
    )

    allocation_percent: float = Field(
        ge=0,
        le=100,
        description="Share of the user's total amount for this position.",
    )

    thesis: str = Field(description="The core argument, in a few sentences.")

    # The next three lists are required and non-empty on purpose. The
    # brief's "Explainable output" requirement says every recommendation
    # must state its assumptions, its evidence, and its key risks, so
    # the schema makes omitting them impossible rather than relying on
    # the model to remember.
    assumptions: list[str] = Field(min_length=1)

    evidence: list[EvidenceItem] = Field(min_length=1)

    key_risks: list[str] = Field(min_length=1)

    # Requirement 3.3 says the debate must visibly sharpen or change the
    # recommendation rather than be decorative. Making this required
    # forces the system to state what the debate actually changed.
    debate_resolution: str = Field(
        description=(
            "What the bull/bear debate changed about this "
            "recommendation, or why it survived unchanged."
        )
    )

    def cash_amount(self, total: float) -> float:
        """Convert this position's percentage into dollars."""

        return round(total * self.allocation_percent / 100, 2)


class PortfolioRecommendation(BaseModel):
    """
    The final answer: a recommendation per candidate, plus how the
    user's money should be split across them.
    """

    summary: str = Field(
        description="The overall recommendation in a short paragraph."
    )

    stocks: list[StockRecommendation] = Field(min_length=1)

    cash_percent: float = Field(
        default=0.0,
        ge=0,
        le=100,
        description="Share deliberately left uninvested.",
    )

    @model_validator(mode="after")
    def reconcile_cash(self):
        """
        Make the split add up without ever failing the parse.

        A hard validation error here would throw away an otherwise good
        analysis because the model's arithmetic drifted by a fraction of
        a percent. Instead the remainder is treated as cash, and
        is_balanced() below lets callers detect a genuinely bad split.
        """

        invested = sum(stock.allocation_percent for stock in self.stocks)

        remainder = round(100.0 - invested, 2)

        # Only fill in cash when the model left it at the default and
        # there is genuinely something left over.
        if self.cash_percent == 0.0 and remainder > 0:
            self.cash_percent = remainder

        return self

    @property
    def total_allocated(self) -> float:
        """Percent of the portfolio accounted for, cash included."""

        return round(
            sum(s.allocation_percent for s in self.stocks) + self.cash_percent,
            2,
        )

    def is_balanced(self, tolerance: float = 0.5) -> bool:
        """True when the split accounts for the whole portfolio."""

        return abs(self.total_allocated - 100.0) <= tolerance

    def draft_digest(self) -> str:
        """
        A compact text view of the draft, for the evaluator to score.

        Sending the rendered report would waste tokens on formatting the
        critic does not need, so this keeps only the substance.
        """

        parts = [f"SUMMARY: {self.summary}", ""]

        for stock in self.stocks:

            parts += [
                f"--- {stock.ticker} ---",
                f"verdict: {stock.verdict.value}",
                f"conviction: {stock.conviction}/5",
                f"allocation: {stock.allocation_percent}%",
                f"thesis: {stock.thesis}",
                "assumptions: " + "; ".join(stock.assumptions),
                "evidence: "
                + "; ".join(
                    f"{e.claim} [{e.source}: {e.detail}]"
                    for e in stock.evidence
                ),
                "key risks: " + "; ".join(stock.key_risks),
                f"debate outcome: {stock.debate_resolution}",
                "",
            ]

        parts.append(f"cash: {self.cash_percent}%")

        return "\n".join(parts)

    def render(self, request: InvestmentRequest) -> str:
        """Format the portfolio as readable text for the CLI."""

        lines = [
            "=" * 60,
            "INVESTMENT RECOMMENDATION",
            "=" * 60,
            "",
            self.summary,
            "",
        ]

        for stock in self.stocks:

            lines += [
                "-" * 60,
                f"{stock.ticker} — {stock.verdict.value.upper()} "
                f"(conviction {stock.conviction}/5)",
                "-" * 60,
                f"Allocation: {stock.allocation_percent:.1f}%  "
                f"(${stock.cash_amount(request.amount):,.2f})",
                "",
                f"Thesis: {stock.thesis}",
                "",
                "Assumptions:",
                *[f"  - {a}" for a in stock.assumptions],
                "",
                "Evidence:",
                *[
                    f"  - {e.claim}\n      source: {e.source}\n"
                    f"      detail: {e.detail}"
                    for e in stock.evidence
                ],
                "",
                "Key risks:",
                *[f"  - {r}" for r in stock.key_risks],
                "",
                f"Debate outcome: {stock.debate_resolution}",
                "",
            ]

        lines += [
            "-" * 60,
            f"Cash: {self.cash_percent:.1f}%  "
            f"(${request.amount * self.cash_percent / 100:,.2f})",
            f"Total allocated: {self.total_allocated:.1f}%",
        ]

        if not self.is_balanced():
            lines.append(
                "WARNING: allocations do not sum to 100%."
            )

        return "\n".join(lines)


# ============================================================
# EVALUATION CONTRACT
# ============================================================


class EvaluationVerdict(str, Enum):
    """Whether a draft recommendation is good enough to release."""

    ACCEPT = "accept"
    REVISE = "revise"


class Evaluation(BaseModel):
    """
    The critic's scoring of a draft recommendation.

    The three scored criteria are taken directly from the brief's
    reflection requirement: evidence quality, risks addressed, and fit
    to the user's constraints.
    """

    evidence_quality: int = Field(
        ge=1,
        le=5,
        description=(
            "Are claims specific and attributed to real sources, "
            "rather than vague or unsourced?"
        ),
    )

    risks_addressed: int = Field(
        ge=1,
        le=5,
        description=(
            "Are the material risks identified and actually reflected "
            "in the verdict and position size?"
        ),
    )

    fit_to_constraints: int = Field(
        ge=1,
        le=5,
        description=(
            "Does it respect the user's amount, risk appetite, horizon "
            "and stated constraints?"
        ),
    )

    verdict: EvaluationVerdict

    critique: str = Field(
        description=(
            "What specifically must change. When the verdict is "
            "'revise' this is the instruction the author will act on."
        )
    )

    @property
    def average_score(self) -> float:
        """Mean of the three criteria, for logging and thresholds."""

        return round(
            (
                self.evidence_quality
                + self.risks_addressed
                + self.fit_to_constraints
            )
            / 3,
            2,
        )

    def summary_line(self) -> str:
        """One-line score summary for the run log."""

        return (
            f"evidence {self.evidence_quality}/5, "
            f"risks {self.risks_addressed}/5, "
            f"fit {self.fit_to_constraints}/5 "
            f"(avg {self.average_score}) -> {self.verdict.value}"
        )
