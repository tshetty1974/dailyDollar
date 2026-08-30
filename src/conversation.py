import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from agent_framework import Agent, AgentSession, ChatOptions
from agent_framework.gemini import GeminiChatClient

from memory.provider import UserMemoryProvider
from models import (
    DEFAULT_HORIZON,
    DEFAULT_RISK_APPETITE,
    Horizon,
    InvestmentRequest,
    PortfolioRecommendation,
    RiskAppetite,
)
from orchestration.investment_orchestrator import run_investment_research
from universe import available_tickers, split_by_grounding


load_dotenv()


# ============================================================
# WHAT ONE TURN PRODUCES
# ============================================================


class TurnPlan(BaseModel):
    """
    The front-door agent's reading of a single user message.

    The investment parameters are kept flat rather than nested as an
    InvestmentRequest. Nested models make the JSON schema harder for the
    model to follow reliably, and keeping them flat lets defaults and
    validation be applied here in Python, where they are predictable.
    """

    reply: str = Field(
        description="What to say to the user, in plain conversational English."
    )

    intent: str = Field(
        description="Either 'analyse' to run a full analysis, or 'chat'."
    )

    tickers: list[str] = Field(default_factory=list)

    amount: float | None = None

    risk_appetite: RiskAppetite | None = None

    horizon: Horizon | None = None

    constraints: list[str] = Field(default_factory=list)


class Turn(BaseModel):
    """The engine's response to one user message."""

    reply: str

    # Set only when an analysis actually ran.
    recommendation: PortfolioRecommendation | None = None

    request: InvestmentRequest | None = None

    # Candidates we hold no filings for, so fundamentals were skipped.
    ungrounded: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


# ============================================================
# THE FRONT-DOOR AGENT
# ============================================================


def build_assistant(user_id: str) -> Agent:
    """
    The agent the user actually talks to.

    It never performs analysis itself. Its job is to hold a
    conversation, work out when the user is asking for an analysis, and
    extract the parameters that analysis needs. The specialists are
    reached through the orchestrator, not through this agent.
    """

    universe = ", ".join(available_tickers())

    return Agent(
        client=GeminiChatClient(
            api_key=os.environ["GEMINI_API_KEY"],
            model="gemini-3.5-flash-lite",
        ),

        name="Investment Assistant",

        # Long-term memory is injected automatically before every run.
        context_providers=[UserMemoryProvider(user_id=user_id)],

        instructions=f"""

You are the front desk of an investment research service. You talk to
the user, and when they want a stock analysed you hand the work to a
team of specialist analysts.

You do NOT analyse stocks yourself. You do not offer opinions on
whether a stock is a good investment, and you never invent figures.

============================================================
WHAT YOU CAN ANALYSE
============================================================

The research team has company filings for these {len(available_tickers())}
companies:

{universe}

Other listed companies can still be analysed on price, news and
macro -- but not on their financial statements, because we hold no
filings for them. If the user asks about one, say so plainly and let
them decide whether to continue.

Never invent a ticker. If you are not sure what company the user
means, ask.

============================================================
STARTING AN ANALYSIS
============================================================

To run an analysis you need, at minimum:

- at least one ticker
- an amount to invest

You also want a risk appetite (conservative, moderate or aggressive)
and a time horizon (short, medium or long), but if the user will not
say, proceed and tell them what you assumed.

If you remember this user's previous objective, OFFER it as a starting
point -- "same as last time, $50,000, moderate, 3+ years?" -- and let
them confirm or change it. Never silently reuse it. Amount, risk and
horizon are chosen per investment: someone can be cautious with their
savings and speculative with a small punt.

Set intent to "analyse" ONLY when you have the tickers and the amount
and the user actually wants the work done now. Otherwise use "chat"
and ask for what is missing.

============================================================
FOLLOW-UP QUESTIONS
============================================================

If you remember a past recommendation and the user asks about it --
"why only 30% in NVDA?", "what were the risks again?" -- answer from
what you remember. Do NOT set intent to "analyse". Re-running the whole
team costs several minutes and real money to answer a question you can
already answer.

Only run a new analysis when the user asks for one, or when they change
the parameters enough that the old answer no longer applies.

============================================================
REQUIRED OUTPUT SHAPE
============================================================

Return JSON with EXACTLY these keys. Do not rename them or add others.

{{
  "reply": "what you say to the user, plain English",
  "intent": "chat" or "analyse",
  "tickers": ["NVDA", "AMD"],
  "amount": 50000,
  "risk_appetite": "conservative" | "moderate" | "aggressive" | null,
  "horizon": "short" | "medium" | "long" | null,
  "constraints": ["No more than 40% in a single position"]
}}

Rules:

- "reply" is always present and always conversational. Never put JSON,
  field names or instructions inside it.
- Use null for risk_appetite and horizon when the user has not said.
- "tickers" is an empty list when none have been mentioned.
- "constraints" holds the user's own rules in their own words.
- When intent is "analyse", your reply should tell the user the work is
  starting and roughly what to expect -- it takes several minutes.

""",
    )


# ============================================================
# THE ENGINE
# ============================================================


class Conversation:
    """
    One user's ongoing conversation.

    Holds the session (this conversation) while the memory provider
    handles everything from previous ones.
    """

    def __init__(self, user_id: str = "default"):

        self.user_id = user_id

        self.assistant = build_assistant(user_id)

        # Short-term memory: the thread of this conversation. Passed to
        # every run so the model can resolve "that one" and "the other".
        self.session = AgentSession()

    async def plan_turn(self, message: str) -> TurnPlan | None:
        """Ask the assistant what this message means. One model call."""

        response = await self.assistant.run(
            message,
            session=self.session,
            options=ChatOptions(
                response_format=TurnPlan,
                max_tokens=2000,
            ),
        )

        try:
            return response.value

        except ValidationError as error:

            print(f">>> could not parse the assistant's reply: {error}")

            return None

    def build_request(self, plan: TurnPlan) -> InvestmentRequest | None:
        """
        Turn an extracted plan into a validated request.

        Returns None when the plan lacks what an analysis needs, which
        the caller treats as "keep talking" rather than an error.
        """

        if not plan.tickers or not plan.amount:
            return None

        try:
            return InvestmentRequest(
                user_id=self.user_id,
                tickers=plan.tickers,
                amount=plan.amount,
                risk_appetite=plan.risk_appetite or DEFAULT_RISK_APPETITE,
                horizon=plan.horizon or DEFAULT_HORIZON,
                constraints=plan.constraints,
            )

        except ValidationError:
            return None

    async def send(self, message: str) -> Turn:
        """
        Handle one user message.

        Either replies conversationally, or runs the full analysis and
        returns the recommendation alongside the reply.
        """

        plan = await self.plan_turn(message)

        if plan is None:
            return Turn(
                reply=(
                    "Sorry, something went wrong on my side. "
                    "Could you say that again?"
                )
            )

        if plan.intent != "analyse":
            return Turn(reply=plan.reply)

        request = self.build_request(plan)

        if request is None:
            # The assistant wanted to analyse but did not gather enough.
            # Its own reply already asks for what is missing.
            return Turn(reply=plan.reply)

        grounded, ungrounded = split_by_grounding(request.tickers)

        return Turn(
            reply=plan.reply,
            request=request,
            ungrounded=ungrounded,
            recommendation=await run_investment_research(request),
        )
