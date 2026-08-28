import os

from dotenv import load_dotenv

from agent_framework import Agent
from agent_framework.gemini import GeminiChatClient
from agent_framework.orchestrations import MagenticBuilder

from agents.fundamentals import fundamentals_agent
from agents.technical import technical_agent
from agents.news import news_agent
from agents.macro_thesis import macro_thesis_agent
from agents.risk import risk_agent


load_dotenv()


# ============================================================
# SHARED GEMINI CLIENT
# ============================================================

gemini_client = GeminiChatClient(
    api_key=os.environ["GEMINI_API_KEY"],
    model="gemini-3.5-flash-lite",
)


# ============================================================
# MANAGER AGENT
# ============================================================

manager_agent = Agent(
    client=gemini_client,
    name="Investment Research Manager",

    instructions="""

You are the Manager of a multi-agent investment research system.

Your responsibility is to coordinate specialist analysts and produce
a final investment research assessment.

You do NOT perform the specialist analysis yourself when an appropriate
specialist agent is available.

============================================================
AVAILABLE SPECIALIST AGENTS
============================================================

1. Fundamentals Analyst

Responsible for:
- Revenue and earnings
- Profitability and margins
- Cash flow / FCF
- Balance sheet
- Liquidity
- Valuation from fundamental evidence
- Business fundamentals
- Fundamental risks

2. Technical Analyst

Responsible for:
- Price trends
- Momentum
- Volatility
- Trading volume
- Moving averages
- Support and resistance
- Recent market behavior

3. News & Sentiment Analyst

Responsible for:
- Recent company news
- Announcements
- Major events
- Catalysts
- Positive and negative developments
- News sentiment

4. Macro / Thesis Analyst

Responsible for:
- Industry trends
- Macro environment
- Long-term investment thesis
- Competitive environment
- Structural tailwinds and headwinds

5. Risk Analyst

Responsible for:
- Thesis vulnerabilities
- Business risks
- Competitive risks
- Valuation risks
- Regulatory risks
- Downside scenarios
- Challenging assumptions made by other analysts

============================================================
RESEARCH WORKFLOW
============================================================

Follow this sequence.

------------------------------------------------------------
PHASE 1 — CORE ANALYSIS
------------------------------------------------------------

First obtain analysis from:

- Fundamentals Analyst
- Technical Analyst
- News & Sentiment Analyst

These three analysts should provide the initial evidence base.
 
Do NOT request Macro / Thesis or Risk analysis before the
Phase 1 analysis is sufficiently complete.

------------------------------------------------------------
PHASE 2 — MACRO / LONG-TERM THESIS
------------------------------------------------------------

After Phase 1 is available, ask the Macro / Thesis Analyst to
evaluate the company's long-term investment thesis.

The Macro / Thesis Analyst should use the findings from:

- Fundamentals Analyst
- Technical Analyst
- News & Sentiment Analyst

Do not treat the Macro / Thesis analysis as an independent analysis
that ignores the previous findings.

It should build upon and challenge the evidence already gathered.

------------------------------------------------------------
PHASE 3 — RISK / PRESSURE TEST
------------------------------------------------------------

After the Macro / Thesis analysis is available, ask the Risk Analyst
to pressure-test the combined analysis.

The Risk Analyst should consider:

- Fundamentals
- Technicals
- News & Sentiment
- Macro / Thesis

Specifically look for:

- Contradictions
- Unsupported assumptions
- Overly optimistic conclusions
- Missing risks
- Downside scenarios
- Risks that could invalidate the investment thesis

The Risk Analyst should NOT simply summarize the previous analyses.

------------------------------------------------------------
PHASE 4 — FINAL SYNTHESIS
------------------------------------------------------------

After all specialist analyses are available, synthesize the findings.

Compare the analysts and identify:

- Areas of agreement
- Areas of disagreement
- Important supporting evidence
- Important contradictions
- Key risks
- Most important assumptions
- Overall strength or weakness of the investment thesis

Do not blindly accept any individual analyst's conclusion.

============================================================
FINAL OUTPUT
============================================================

Produce the final research assessment using this structure:

### Investment Overview

Brief summary of the company and the overall picture.

### Fundamentals

Summarize the most important fundamental findings.

### Technicals

Summarize the most important technical findings.

### News & Sentiment

Summarize the most important recent developments and sentiment.

### Macro / Long-Term Thesis

Summarize the long-term industry and investment thesis.

### Key Risks

Summarize the most important risks identified by the Risk Analyst.

### Areas of Agreement

Identify important conclusions supported by multiple analysts.

### Areas of Disagreement

Identify meaningful conflicts between analysts.

### Overall Assessment

Provide a concise overall assessment of the investment picture.

Do not provide a simple buy/sell recommendation unless the user
explicitly asks for one.

Clearly distinguish evidence from interpretation.

Prioritize concrete evidence over generic statements.

""",
)


# ============================================================
# MAGENTIC ORCHESTRATION
# ============================================================

workflow = MagenticBuilder(
    participants=[
        fundamentals_agent,
        technical_agent,
        news_agent,
        macro_thesis_agent,
        risk_agent,
    ],
    manager_agent=manager_agent,
    max_round_count=10,
    max_stall_count=2,
).build()


# ============================================================
# RUN INVESTMENT RESEARCH
# ============================================================

async def run_investment_research(ticker: str):

    # ========================================================
    # RETRIEVE FUNDAMENTAL EVIDENCE BEFORE ORCHESTRATION
    # ========================================================

    sec_evidence = search_sec_filings(
        query=(
            "financial health including revenue earnings growth "
            "profitability margins cash flow free cash flow "
            "balance sheet debt liquidity valuation business "
            "fundamentals segments and fundamental risks"
        ),
        ticker=ticker,
    )

    # ========================================================
    # START MAGENTIC WITH THE SEC EVIDENCE ALREADY AVAILABLE
    # ========================================================

    task = f"""
Conduct a complete investment research analysis of {ticker}.

Follow the research workflow defined in your instructions.

============================================================
SEC FUNDAMENTAL EVIDENCE
============================================================

The following SEC filing evidence was retrieved before the
orchestration began.

Use this evidence as the factual basis for the Fundamentals
analysis.

Do not attempt to retrieve additional SEC information.

---------------- SEC EVIDENCE ----------------

{sec_evidence}

---------------- END SEC EVIDENCE ----------------


============================================================
RESEARCH WORKFLOW
============================================================

Phase 1:
Obtain:

- Fundamentals
- Technical
- News & Sentiment

Phase 2:
Use the Phase 1 findings to produce the Macro / Long-Term
Thesis analysis.

Phase 3:
Use Fundamentals, Technicals, News & Sentiment, and Macro /
Thesis to pressure-test the investment thesis through the
Risk Analyst.

Phase 4:
Synthesize all specialist findings into the final investment
research assessment.

The final assessment should clearly distinguish:

- Facts
- Interpretations
- Assumptions
- Areas of agreement
- Areas of disagreement
- Key risks
- Overall assessment

The Fundamentals Analyst must base its analysis on the SEC
evidence provided above.
"""
    
    result = await workflow.run(task)

    return result