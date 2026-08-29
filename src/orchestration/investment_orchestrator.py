import os

from dotenv import load_dotenv
from pydantic import ValidationError

from agent_framework import Agent, ChatOptions
from agent_framework.gemini import GeminiChatClient
from agent_framework.orchestrations import MagenticBuilder

from agents.fundamentals import fundamentals_agent
from agents.technical import technical_agent, market_tool
from agents.news import news_agent
from agents.macro_thesis import macro_thesis_agent
from agents.risk import risk_agent
from agents.bull import bull_agent
from agents.synthesis import synthesis_agent
from agents.evaluator import evaluator_agent

from models import (
    Evaluation,
    EvaluationVerdict,
    InvestmentRequest,
    PortfolioRecommendation,
)

from tools.sec_tools import search_sec_filings


load_dotenv()


# ============================================================
# SHARED GEMINI CLIENT
# ============================================================

gemini_client = GeminiChatClient(
    api_key=os.environ["GEMINI_API_KEY"],
    model="gemini-3.5-flash-lite",
)


# The names must match the agents' own `name=` values, because that is
# what appears as executor_id on the workflow events we harvest.
# Generous enough that a multi-stock recommendation cannot be cut off
# mid-object, which would produce unparseable JSON.
SYNTHESIS_MAX_TOKENS = 8000


PARTICIPANT_NAMES = [
    "Fundamentals Analyst",
    "Technical Analyst",
    "News & Sentiment Analyst",
    "Macro & Investment Thesis Analyst",
    "Risk Analyst",
]


# The manager's Phase 4 consolidation and the debate transcript are
# stored alongside the specialists' findings so that everything reaches
# the synthesis step through the same channel.
MANAGER_KEY = "Research Manager — consolidation"

DEBATE_KEY = "Bull vs Skeptic Debate"

FINDING_SECTIONS = PARTICIPANT_NAMES + [MANAGER_KEY, DEBATE_KEY]


# One revision only. The brief asks for a reflection loop but also for
# guards against unbounded loops, and a critic that can always demand
# another pass is an unbounded cost.
MAX_REVISIONS = 1


# ============================================================
# MANAGER AGENT
# ============================================================

manager_agent = Agent(
    client=gemini_client,

    name="Investment Research Manager",

    instructions="""

You are the Manager of a multi-agent investment research system.

You coordinate specialist analysts and decide when enough evidence has
been gathered. You do NOT perform specialist analysis yourself, and you
do NOT decide position sizes — a separate Synthesis & Allocation
Analyst owns the final recommendation.

============================================================
AVAILABLE SPECIALIST AGENTS
============================================================

1. Fundamentals Analyst — revenue, earnings, margins, cash flow,
   balance sheet, liquidity, valuation, fundamental risks.

   The Fundamentals Analyst receives SEC filing evidence in the task
   context and has no SEC retrieval tool. Pass that evidence along when
   you delegate, and do not ask this analyst to retrieve filings.

2. Technical Analyst — price trends, momentum, volatility, volume,
   moving averages, support and resistance.

   The Technical Analyst has live market-data tools and should use
   them.

3. News & Sentiment Analyst — recent news, announcements, catalysts,
   sentiment.

4. Macro & Investment Thesis Analyst — industry trends, macro
   environment, competitive position, long-term thesis.

5. Risk Analyst — thesis vulnerabilities, downside scenarios, and
   challenges to the other analysts' assumptions.

============================================================
RESEARCH WORKFLOW
============================================================

PHASE 1 — CORE ANALYSIS
Obtain Fundamentals, Technical, and News & Sentiment. These form the
evidence base. Do not move on until all three have reported.

PHASE 2 — MACRO / THESIS
Give the Phase 1 findings to the Macro & Investment Thesis Analyst.

PHASE 3 — RISK / PRESSURE TEST
Give all prior findings to the Risk Analyst, who should look for
contradictions, unsupported assumptions, overly optimistic
conclusions, missing risks, and anything that would invalidate the
thesis.

PHASE 4 — CONFIRM COMPLETENESS
Once all five analysts have reported, briefly note the areas of
agreement, the areas of disagreement, and the open questions. Then
stop.

Do NOT produce a buy/sell recommendation and do NOT suggest position
sizes. That is the Synthesis & Allocation Analyst's job and it happens
after you finish.

============================================================
FACTUAL DISCIPLINE
============================================================

Keep facts, interpretations, and assumptions clearly separated.
Do not fabricate evidence or financial figures.

""",
)


# ============================================================
# WORKFLOW
# ============================================================

def build_workflow():
    """
    Construct a fresh Magentic workflow.

    A new workflow is built per stock rather than shared, so that one
    candidate's conversation cannot leak into the next one's analysis.
    """

    return MagenticBuilder(
        participants=[
            fundamentals_agent,
            technical_agent,
            news_agent,
            macro_thesis_agent,
            risk_agent,
        ],
        manager_agent=manager_agent,

        # Five analysts across four phases needs considerably more than
        # the previous budget of 10, which ran out before the manager
        # could close the loop.
        max_round_count=25,
        max_stall_count=3,
    ).build()


# ============================================================
# HARVESTING FINDINGS FROM WORKFLOW EVENTS
# ============================================================

def _response_texts(data):
    """
    Yield any response text hiding inside a workflow event payload.

    Event payloads are inconsistent: sometimes a single response,
    sometimes a list, and sometimes an AgentExecutorResponse wrapping
    the real response. This normalises all three.
    """

    if data is None:
        return

    items = data if isinstance(data, (list, tuple)) else [data]

    for item in items:

        # AgentExecutorResponse wraps the actual agent response.
        inner = getattr(item, "agent_response", None)

        candidate = inner if inner is not None else item

        text = getattr(candidate, "text", None)

        if text and text.strip():
            yield text.strip()


def collect_findings(events) -> dict[str, list[str]]:
    """
    Pull each specialist's actual output out of the workflow events.

    We harvest the participants' own responses rather than the
    manager's closing summary, because the summary compresses away the
    specific figures and filing references that the final
    recommendation needs in order to cite its sources.
    """

    findings: dict[str, list[str]] = {
        name: [] for name in PARTICIPANT_NAMES
    }

    for event in events:

        executor_id = getattr(event, "executor_id", None)

        if executor_id not in findings:
            continue

        for text in _response_texts(getattr(event, "data", None)):

            # The same response can surface on more than one event.
            if text not in findings[executor_id]:
                findings[executor_id].append(text)

    return findings


def final_text(events) -> str | None:
    """Return the workflow's own final answer, if it produced one."""

    for event in events:

        if getattr(event, "type", None) == "output":

            for text in _response_texts(getattr(event, "data", None)):
                return text

    return None


# ============================================================
# PER-STOCK RESEARCH
# ============================================================

def build_task(request: InvestmentRequest, ticker: str, sec_evidence: str) -> str:
    """Compose the orchestration task for one candidate stock."""

    return f"""

Conduct a complete investment research analysis of {ticker}.

{request.objective_brief()}

============================================================
SEC EVIDENCE — FOR THE FUNDAMENTALS ANALYST
============================================================

The following was retrieved from {ticker}'s SEC filings before this
analysis began. Pass it to the Fundamentals Analyst, who has no
retrieval tool of their own and must use it as their factual basis.

---------------- BEGIN SEC EVIDENCE ----------------

{sec_evidence}

---------------- END SEC EVIDENCE ----------------

The Technical, News & Sentiment, Macro, and Risk analysts should
perform their own independent analysis of {ticker}.

Work through Phases 1 to 4 in order. Do not produce a buy/sell
recommendation or a position size — those come later.

""".strip()


async def research_stock(request: InvestmentRequest, ticker: str) -> dict[str, list[str]]:
    """
    Run the full specialist orchestration for one candidate stock.

    Assumes the market-data MCP session is already open; the caller
    holds it open across every stock in the run.
    """

    print(f"\n>>> [{ticker}] RETRIEVING SEC EVIDENCE")

    sec_evidence = search_sec_filings(
        query=(
            "financial health including revenue earnings growth "
            "profitability margins cash flow free cash flow "
            "balance sheet debt liquidity valuation business "
            "fundamentals segments and fundamental risks"
        ),
        ticker=ticker,
    )

    print(f">>> [{ticker}] SEC EVIDENCE: {len(sec_evidence)} characters")

    task = build_task(request, ticker, sec_evidence)

    print(f">>> [{ticker}] STARTING MAGENTIC ORCHESTRATION")

    workflow = build_workflow()

    events = await workflow.run(task)

    findings = collect_findings(events)

    # The specialists' raw text is kept for its figures and citations,
    # but the manager's Phase 4 consolidation is worth keeping too: it
    # is the only place the analysts are reconciled against each other,
    # naming agreements, disagreements and open questions.
    manager_summary = final_text(events)

    if manager_summary:
        findings[MANAGER_KEY] = [manager_summary]

    reported = [name for name in PARTICIPANT_NAMES if findings.get(name)]

    print(
        f">>> [{ticker}] ORCHESTRATION COMPLETE — "
        f"{len(reported)}/{len(PARTICIPANT_NAMES)} analysts reported"
        + ("" if manager_summary else " (no manager consolidation captured)")
    )

    for name in PARTICIPANT_NAMES:
        if not findings[name]:
            print(f"    WARNING: no output captured from {name}")

    return findings


# ============================================================
# STRUCTURED DEBATE
# ============================================================

def findings_digest(findings: dict[str, list[str]]) -> str:
    """Flatten one stock's specialist findings into debate context."""

    parts = []

    for name in PARTICIPANT_NAMES:

        for text in findings.get(name, []):
            parts.append(f"--- {name} ---\n{text}")

    return "\n\n".join(parts)


async def run_debate(
    ticker: str,
    findings: dict[str, list[str]],
    request: InvestmentRequest,
) -> list[str]:
    """
    Run a three-turn bull vs skeptic debate on one candidate.

    The debate is run explicitly rather than left to the Magentic
    manager to arrange. The manager decides for itself whether an
    exchange is worth having, so a genuine back-and-forth could not be
    guaranteed; requirement 3.3 asks for one every time. Running it
    directly also makes the transcript easy to capture and pass on.
    """

    print(f">>> [{ticker}] DEBATE — bull opens")

    context = findings_digest(findings)

    opening = await bull_agent.run(
        f"""
{request.objective_brief()}

Make the strongest honest case FOR investing in {ticker}, based on the
specialist findings below.

============================================================
SPECIALIST FINDINGS — {ticker}
============================================================

{context}
""".strip()
    )

    bull_case = getattr(opening, "text", "") or ""

    print(f">>> [{ticker}] DEBATE — skeptic rebuts")

    rebuttal = await risk_agent.run(
        f"""
You are acting as the skeptic in a formal debate about {ticker}.

The Bull Analyst has made the case below. Attack it.

Identify its weakest assumptions, the risks it understates or ignores,
and the conditions under which it fails. Be specific about which part
of the argument you are attacking.

============================================================
THE BULL CASE
============================================================

{bull_case}

============================================================
SPECIALIST FINDINGS — {ticker}
============================================================

{context}
""".strip()
    )

    bear_case = getattr(rebuttal, "text", "") or ""

    print(f">>> [{ticker}] DEBATE — bull responds")

    response = await bull_agent.run(
        f"""
The skeptic has attacked your case for {ticker} as set out below.

Respond. Concede the objections that genuinely land, and explain why
the remaining ones do not break the thesis. Where an objection defeats
part of your case, say so and narrow your claim.

============================================================
YOUR ORIGINAL CASE
============================================================

{bull_case}

============================================================
THE SKEPTIC'S ATTACK
============================================================

{bear_case}
""".strip()
    )

    bull_reply = getattr(response, "text", "") or ""

    return [
        f"[BULL — opening case for {ticker}]\n{bull_case}",
        f"[SKEPTIC — rebuttal on {ticker}]\n{bear_case}",
        f"[BULL — response to the rebuttal on {ticker}]\n{bull_reply}",
    ]


# ============================================================
# SYNTHESIS
# ============================================================

def build_synthesis_prompt(
    request: InvestmentRequest,
    all_findings: dict[str, dict[str, list[str]]],
    critique: str | None = None,
    previous_draft: PortfolioRecommendation | None = None,
) -> str:
    """
    Lay out every specialist's findings for the synthesis agent.

    `critique` marks a revision demanded by the evaluator.

    `previous_draft` is the pre-debate draft. Supplying it turns this
    into the post-debate pass, where the agent is shown its own earlier
    conclusion and asked to reconsider it in light of the debate.
    """

    sections = []

    for ticker, findings in all_findings.items():

        sections.append(f"\n{'=' * 60}\nCANDIDATE: {ticker}\n{'=' * 60}")

        for section_name in FINDING_SECTIONS:

            for text in findings.get(section_name, []):
                sections.append(
                    f"\n---------- {section_name} — {ticker} ----------\n{text}"
                )

    prior_block = (
        f"""

============================================================
YOUR PRE-DEBATE DRAFT — RECONSIDER IT
============================================================

Before the bull and skeptic debated, you reached this conclusion:

{previous_draft.draft_digest()}

The debate transcripts above happened AFTER that draft.

Reconsider each position in light of what the debate established:

- Where the skeptic landed a real blow, change the verdict, the
  conviction, or the allocation accordingly. Do not defend your earlier
  number out of consistency.
- Where the bull successfully answered the objection, you may keep or
  raise your position.
- In "debate_resolution", state concretely what changed against the
  draft above and why — for example "allocation cut from 40% to 25%
  because the skeptic showed the volatility is inconsistent with a
  moderate risk appetite" — or state plainly that the position survived
  the debate intact, and why the objections were not decisive.
"""
        if previous_draft
        else ""
    )

    revision_block = (
        f"""

============================================================
REVISION REQUIRED — ADDRESS THIS CRITIQUE
============================================================

An evaluator reviewed your previous draft and rejected it.

{critique}

Produce a corrected recommendation that fixes each point above. Keep
whatever was sound; change only what the critique identifies.
"""
        if critique
        else ""
    )

    return f"""

{request.objective_brief()}

============================================================
SPECIALIST RESEARCH FINDINGS
============================================================
{"".join(sections)}

============================================================
YOUR TASK
============================================================

Produce the final recommendation for all {len(request.tickers)}
candidate(s), and allocate the user's ${request.amount:,.2f} across
them.

Base every piece of evidence on the findings above and name its
source. Do not introduce figures that do not appear above.

============================================================
REQUIRED OUTPUT SHAPE
============================================================

Return JSON with EXACTLY these keys. Do not rename them, do not nest
them differently, and do not add keys of your own.

{{
  "summary": "string — the overall recommendation in a short paragraph",
  "stocks": [
    {{
      "ticker": "string",
      "verdict": "one of: buy, accumulate, hold, avoid",
      "conviction": 3,
      "allocation_percent": 25.0,
      "thesis": "string — the core argument in plain language",
      "assumptions": ["string", "at least one required"],
      "evidence": [
        {{
          "claim": "string — the factual claim",
          "source": "string — e.g. '10-K 2026-02-25, Item 1A'",
          "detail": "string — the figure or quotation behind it"
        }}
      ],
      "key_risks": ["string", "at least one required"],
      "debate_resolution": "string — what the bull/skeptic debate changed"
    }}
  ],
  "cash_percent": 15.0
}}

Rules:

- The top-level keys are "summary", "stocks", and "cash_percent".
  Nothing else.
- "stocks" must contain one entry per candidate.
- "conviction" is a whole number from 1 to 5.
- "assumptions", "evidence", and "key_risks" must each contain at
  least one entry.
- Every evidence entry must fill in all three of claim, source and
  detail.
- allocation_percent values plus cash_percent should total 100.
- If the findings above contain no bull/skeptic debate, then
  "debate_resolution" must say exactly that — for example "No debate
  was conducted for this candidate." Do NOT relabel a single analyst's
  findings as a debate.
{prior_block}{revision_block}
""".strip()


async def synthesise(
    request: InvestmentRequest,
    all_findings: dict[str, dict[str, list[str]]],
    critique: str | None = None,
    previous_draft: PortfolioRecommendation | None = None,
) -> PortfolioRecommendation | None:
    """
    Turn the gathered findings into the final structured recommendation.

    response_format is passed here, at call time, because that is the
    path that reliably returns a parsed object on `.value`.
    """

    print("\n>>> SYNTHESISING FINAL RECOMMENDATION")

    prompt = build_synthesis_prompt(
        request,
        all_findings,
        critique,
        previous_draft,
    )

    options = ChatOptions(
        response_format=PortfolioRecommendation,

        # Left unset, a multi-stock answer can run past the default
        # ceiling and stop mid-object. That yields invalid JSON rather
        # than a missing field, which is unrecoverable, so the budget is
        # set generously.
        max_tokens=SYNTHESIS_MAX_TOKENS,
    )

    response = await synthesis_agent.run(prompt, options=options)

    # `.value` re-parses the response text and raises on a mismatch, so
    # it must be guarded rather than defaulted with getattr.
    try:
        return response.value

    except ValidationError as error:

        failed_text = getattr(response, "text", "") or ""
        failure_detail = str(error)

        print(">>> synthesis output failed validation — attempting repair")
        print(failure_detail)

    # The repair runs outside the except block so the exception object
    # is not kept alive, and deliberately does NOT resend the research
    # findings: reshaping malformed JSON is a formatting task, and
    # resending every analyst's output would roughly double the cost of
    # an already expensive run.
    repair_prompt = f"""

Your previous response did not match the required output shape.

------------------ YOUR PREVIOUS OUTPUT ------------------

{failed_text}

------------------ VALIDATION ERRORS ------------------

{failure_detail}

------------------ WHAT TO DO ------------------

Return the SAME analysis, corrected so that it satisfies the schema.

Do not change your conclusions, allocations, or evidence. Only fix the
structure so that it validates.

Return JSON only, with the top-level keys "summary", "stocks", and
"cash_percent", and nothing else.

""".strip()

    repair = await synthesis_agent.run(repair_prompt, options=options)

    try:
        recommendation = repair.value

        print(">>> repair succeeded")

        return recommendation

    except ValidationError as error:

        print(">>> repair failed; giving up on structured output")
        print(error)
        print("\n>>> RAW TEXT FOLLOWS:\n")
        print(getattr(repair, "text", "(no text)"))

        return None


# ============================================================
# REFLECTION / EVALUATION
# ============================================================

async def evaluate(
    request: InvestmentRequest,
    draft: PortfolioRecommendation,
) -> Evaluation | None:
    """
    Score a draft recommendation against the brief's three criteria.

    Returns None when the critic's own output cannot be parsed, which
    the caller treats as "no objection" rather than failing the run: a
    broken critic should not be able to discard a sound analysis.
    """

    print("\n>>> EVALUATING DRAFT")

    prompt = f"""

{request.objective_brief()}

============================================================
DRAFT RECOMMENDATION TO EVALUATE
============================================================

{draft.draft_digest()}

============================================================
YOUR TASK
============================================================

Score this draft on evidence quality, risks addressed, and fit to the
user's constraints. Then decide whether to accept it or send it back
for revision, and say specifically what must change.

Return JSON with EXACTLY these keys and nothing else:

{{
  "evidence_quality": 4,
  "risks_addressed": 3,
  "fit_to_constraints": 5,
  "verdict": "accept" or "revise",
  "critique": "string — specific and actionable"
}}

""".strip()

    response = await evaluator_agent.run(
        prompt,
        options=ChatOptions(
            response_format=Evaluation,
            max_tokens=2000,
        ),
    )

    try:
        evaluation = response.value

    except ValidationError as error:

        print(">>> evaluator output could not be parsed; skipping review")
        print(error)

        return None

    print(f">>> EVALUATION: {evaluation.summary_line()}")

    return evaluation


# ============================================================
# DEBATE IMPACT
# ============================================================

def debate_impact_report(
    before: PortfolioRecommendation,
    after: PortfolioRecommendation,
) -> str:
    """
    Compare the pre-debate and post-debate recommendations.

    This is what makes the debate demonstrably non-decorative. Both
    drafts were produced from identical research; the only thing that
    changed between them was the bull/skeptic exchange, so any
    difference here is attributable to the debate.
    """

    before_by_ticker = {stock.ticker: stock for stock in before.stocks}

    lines = ["=" * 60, "DEBATE IMPACT", "=" * 60]

    changed = False

    for stock in after.stocks:

        prior = before_by_ticker.get(stock.ticker)

        if prior is None:
            lines.append(f"{stock.ticker}: not present in the pre-debate draft")
            changed = True
            continue

        deltas = []

        if prior.allocation_percent != stock.allocation_percent:
            deltas.append(
                f"allocation {prior.allocation_percent:.1f}% -> "
                f"{stock.allocation_percent:.1f}%"
            )

        if prior.conviction != stock.conviction:
            deltas.append(
                f"conviction {prior.conviction} -> {stock.conviction}"
            )

        if prior.verdict != stock.verdict:
            deltas.append(
                f"verdict {prior.verdict.value} -> {stock.verdict.value}"
            )

        if deltas:
            changed = True
            lines.append(f"{stock.ticker}: " + ", ".join(deltas))
        else:
            lines.append(f"{stock.ticker}: unchanged by the debate")

    if before.cash_percent != after.cash_percent:
        changed = True
        lines.append(
            f"cash {before.cash_percent:.1f}% -> {after.cash_percent:.1f}%"
        )

    if not changed:
        lines.append("(the debate did not alter any position)")

    return "\n".join(lines)


# ============================================================
# ENTRY POINT
# ============================================================

async def run_investment_research(
    request: InvestmentRequest,
) -> PortfolioRecommendation | None:
    """
    Research every candidate, draft a recommendation, debate it, redraft
    in light of the debate, then have the result critiqued.

    Synthesis runs twice on purpose. The first pass is made without the
    debate, the second with it, so the difference between them is
    attributable to the debate alone. That turns "the debate influenced
    the outcome" from a claim into an observable diff.
    """

    all_findings: dict[str, dict[str, list[str]]] = {}

    # --- phase 1: research ----------------------------------------
    #
    # One MCP session for the whole research phase. The Technical
    # Analyst reaches the market-data server over stdio, and that
    # subprocess has to stay alive for every round of every stock.
    async with market_tool:

        for ticker in request.tickers:

            all_findings[ticker] = await research_stock(request, ticker)

    # --- phase 2: pre-debate draft --------------------------------

    print("\n>>> DRAFTING PRE-DEBATE RECOMMENDATION")

    pre_debate = await synthesise(request, all_findings)

    # --- phase 3: debate ------------------------------------------

    for ticker in request.tickers:

        all_findings[ticker][DEBATE_KEY] = await run_debate(
            ticker,
            all_findings[ticker],
            request,
        )

    # --- phase 4: post-debate recommendation ----------------------

    print("\n>>> REDRAFTING IN LIGHT OF THE DEBATE")

    recommendation = await synthesise(
        request,
        all_findings,
        previous_draft=pre_debate,
    )

    # If the post-debate pass fails to parse, the pre-debate draft is
    # still a usable answer and is better than returning nothing.
    if recommendation is None:
        recommendation = pre_debate

    if recommendation is None:
        return None

    if pre_debate is not None and pre_debate is not recommendation:
        print("\n" + debate_impact_report(pre_debate, recommendation))

    for attempt in range(MAX_REVISIONS):

        evaluation = await evaluate(request, recommendation)

        if evaluation is None:
            break

        if evaluation.verdict is EvaluationVerdict.ACCEPT:
            print(">>> DRAFT ACCEPTED BY EVALUATOR")
            break

        print(f">>> REVISING (attempt {attempt + 1} of {MAX_REVISIONS})")
        print(f">>> CRITIQUE: {evaluation.critique}")

        revised = await synthesise(
            request,
            all_findings,
            critique=evaluation.critique,
        )

        # Keep the draft we already have if the revision fails to
        # parse; a failed rewrite should not lose a usable answer.
        if revised is not None:
            recommendation = revised

    return recommendation
