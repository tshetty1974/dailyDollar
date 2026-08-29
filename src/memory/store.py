"""
Long-term memory: the part of the system that survives the process.

Everything else in this project lives in variables and disappears when
the program exits. This module writes a small JSON file per user so the
next session can pick up where the last one ended -- the user's profile
and constraints, what they hold, and every recommendation ever made for
them.

That is the whole of "long-term memory": a file on disk, read at the
start of a session and written at the end of each analysis.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from models import InvestmentRequest, PortfolioRecommendation


MEMORY_DIR = Path("data/memory")


# ============================================================
# WHAT WE REMEMBER
# ============================================================


class PastRecommendation(BaseModel):
    """One completed analysis, kept so it can be discussed later."""

    timestamp: str

    # The whole objective is stored, not just the tickers and amount.
    # Risk appetite, horizon and constraints are decided per investment
    # -- a small speculative punt and a large cautious one are different
    # requests from the same person -- so each analysis has to carry the
    # parameters it was actually run under. Otherwise "why was that one
    # so aggressive?" is unanswerable.
    request: InvestmentRequest

    recommendation: PortfolioRecommendation

    def headline(self) -> str:
        """One line describing this recommendation, for recall."""

        positions = ", ".join(
            f"{stock.ticker} {stock.allocation_percent:.0f}% "
            f"({stock.verdict.value})"
            for stock in self.recommendation.stocks
        )

        return (
            f"{self.timestamp[:10]} — ${self.request.amount:,.0f}, "
            f"{self.request.risk_appetite.value}/"
            f"{self.request.horizon.value} — {positions}, "
            f"{self.recommendation.cash_percent:.0f}% cash"
        )


class UserMemory(BaseModel):
    """
    Everything the system knows about one user, across all sessions.

    Keyed by user_id even though the system serves a single user today,
    so supporting more users is a storage concern rather than a
    redesign.
    """

    user_id: str

    # The most recent objective. This is a DEFAULT TO OFFER, not a fixed
    # profile: amount, risk appetite, horizon and constraints are chosen
    # per investment, so the right behaviour is to propose these back and
    # let the user confirm or change them -- never to assume them.
    last_request: InvestmentRequest | None = None

    # Ticker -> dollars currently held.
    holdings: dict[str, float] = Field(default_factory=dict)

    # Newest last.
    history: list[PastRecommendation] = Field(default_factory=list)

    # --------------------------------------------------------
    # Updating
    # --------------------------------------------------------

    def remember(
        self,
        request: InvestmentRequest,
        recommendation: PortfolioRecommendation,
    ) -> None:
        """
        Record a completed analysis.

        Called as soon as an analysis finishes rather than at the end of
        the session, so that a follow-up question is answerable from the
        store whether it arrives ten seconds or ten days later. That
        keeps same-session and cross-session recall on one code path.
        """

        self.last_request = request

        self.history.append(
            PastRecommendation(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request=request,
                recommendation=recommendation,
            )
        )

        for stock in recommendation.stocks:
            self.holdings[stock.ticker] = stock.cash_amount(request.amount)

    # --------------------------------------------------------
    # Recall
    # --------------------------------------------------------

    def latest(self) -> PastRecommendation | None:
        """The most recent analysis, if there is one."""

        return self.history[-1] if self.history else None

    def recall_brief(self) -> str:
        """
        Render what we know as prompt text.

        This is what makes follow-up questions answerable without the
        user restating anything: it is injected into the conversational
        agent so the model can see the history it is being asked about.
        """

        if self.last_request is None and not self.history:
            return "No previous sessions with this user."

        parts = [f"WHAT WE KNOW ABOUT THIS USER (user_id: {self.user_id})", ""]

        if self.last_request is not None:
            parts += [
                "Most recent objective — OFFER THESE AS DEFAULTS, DO NOT ASSUME THEM.",
                "The user chooses amount, risk appetite, horizon and constraints",
                "separately for each investment, so confirm before reusing them:",
                f"- Amount: ${self.last_request.amount:,.2f}",
                f"- Risk appetite: {self.last_request.risk_appetite.value}",
                f"- Time horizon: {self.last_request.horizon.value}",
                "- Constraints: "
                + (
                    "; ".join(self.last_request.constraints)
                    if self.last_request.constraints
                    else "none stated"
                ),
                "",
            ]

        if self.holdings:
            parts += [
                "Current holdings:",
                *[
                    f"- {ticker}: ${value:,.2f}"
                    for ticker, value in self.holdings.items()
                ],
                "",
            ]

        if self.history:

            parts.append(f"Past recommendations ({len(self.history)} total):")

            # Only the last few are summarised; the full detail of the
            # most recent one follows, since that is what follow-up
            # questions almost always refer to.
            for past in self.history[-5:]:
                parts.append(f"- {past.headline()}")

            latest = self.history[-1]

            parts += [
                "",
                "MOST RECENT RECOMMENDATION IN FULL",
                "(produced under the parameters shown, which may differ "
                "from any new request):",
                "",
                f"Run with: ${latest.request.amount:,.2f}, "
                f"{latest.request.risk_appetite.value} risk, "
                f"{latest.request.horizon.value} horizon, "
                + (
                    "constraints: " + "; ".join(latest.request.constraints)
                    if latest.request.constraints
                    else "no constraints"
                ),
                "",
                latest.recommendation.draft_digest(),
            ]

        return "\n".join(parts)


# ============================================================
# READING AND WRITING THE FILE
# ============================================================


def memory_path(user_id: str) -> Path:
    """Where this user's memory file lives."""

    return MEMORY_DIR / f"{user_id}.json"


def load_memory(user_id: str = "default") -> UserMemory:
    """
    Read a user's memory from disk.

    A missing or unreadable file yields empty memory rather than an
    error: a first-time user and a corrupted file should both leave the
    system usable, just without history.
    """

    path = memory_path(user_id)

    if not path.exists():
        return UserMemory(user_id=user_id)

    try:
        return UserMemory.model_validate_json(path.read_text())

    except Exception as error:

        print(f">>> WARNING: could not read memory for {user_id}: {error}")
        print(">>> continuing with empty memory")

        return UserMemory(user_id=user_id)


def save_memory(memory: UserMemory) -> None:
    """
    Write a user's memory to disk.

    Written to a temporary file and then moved into place, so an
    interruption mid-write cannot leave a half-written file that would
    lose every past recommendation.
    """

    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    path = memory_path(memory.user_id)

    temporary = path.with_suffix(".json.tmp")

    temporary.write_text(
        json.dumps(
            memory.model_dump(mode="json"),
            indent=2,
        )
    )

    temporary.replace(path)
