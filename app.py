import asyncio
import sys
from pathlib import Path

import streamlit as st


# src/ has to be importable, and tracing has to be configured before the
# agent modules load, exactly as in main.py: the tracer provider must
# exist before anything grabs a tracer or no spans are produced.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from observability import setup_observability  # noqa: E402

setup_observability(live=False)

from conversation import Conversation  # noqa: E402
from models import InvestmentRequest, PortfolioRecommendation  # noqa: E402
from universe import available_tickers  # noqa: E402


st.set_page_config(page_title="Investment Research", page_icon="📈")


# ============================================================
# RENDERING
# ============================================================


def render_recommendation(
    recommendation: PortfolioRecommendation,
    request: InvestmentRequest,
) -> str:
    """
    Format a recommendation as markdown.

    The terminal renderer uses fixed-width alignment, which looks wrong
    in a browser, so the same data is laid out again for this medium.
    """

    parts = [
        f"### Recommendation for ${request.amount:,.0f}",
        "",
        recommendation.summary,
        "",
    ]

    for stock in recommendation.stocks:

        parts += [
            "---",
            f"#### {stock.ticker} — {stock.verdict.value.upper()}",
            "",
            f"**{stock.allocation_percent:.0f}%** "
            f"(${stock.cash_amount(request.amount):,.0f}) · "
            f"conviction {stock.conviction}/5",
            "",
            stock.thesis,
            "",
            "**Evidence**",
            "",
        ]

        for item in stock.evidence:
            parts.append(
                f"- {item.claim}  \n"
                f"  *{item.source}* — {item.detail}"
            )

        parts += ["", "**Key risks**", ""]
        parts += [f"- {risk}" for risk in stock.key_risks]

        parts += ["", "**Assumptions**", ""]
        parts += [f"- {assumption}" for assumption in stock.assumptions]

        parts += [
            "",
            f"**What the debate changed:** {stock.debate_resolution}",
            "",
        ]

    parts += [
        "---",
        f"**Cash:** {recommendation.cash_percent:.0f}% "
        f"(${request.amount * recommendation.cash_percent / 100:,.0f})",
    ]

    if not recommendation.is_balanced():
        parts.append("")
        parts.append("⚠️ Allocations do not sum to 100%.")

    return "\n".join(parts)


# ============================================================
# STATE
# ============================================================

# Streamlit re-runs this script on every interaction, so anything that
# must survive a turn lives in session_state. The Conversation object
# in particular holds the AgentSession -- rebuilding it each rerun would
# reset the short-term memory and break follow-up questions.

if "conversation" not in st.session_state:
    st.session_state.conversation = Conversation(user_id="default")

if "history" not in st.session_state:
    st.session_state.history = []


# ============================================================
# PAGE
# ============================================================

st.title("📈 Investment Research")

st.caption(
    "A team of specialist analysts researches each candidate, debates it, "
    "and returns a recommendation with a suggested allocation."
)

with st.sidebar:

    st.subheader("Companies with filings")

    st.caption(
        "Fundamentals can only be grounded for these. Other tickers are "
        "analysed on price, news and macro only."
    )

    st.write(", ".join(available_tickers()))

    st.divider()

    st.caption(
        "Progress and the OpenTelemetry trace are printed to the terminal "
        "running this app, and written to data/traces/last_run.log."
    )


for entry in st.session_state.history:

    with st.chat_message(entry["role"]):

        st.markdown(entry["content"])

        if entry.get("report"):
            st.markdown(entry["report"])


if prompt := st.chat_input("I have $50k, fairly cautious, 5 years out..."):

    st.session_state.history.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):

        with st.spinner("Thinking..."):

            try:
                # A full analysis takes several minutes; the spinner is
                # the only feedback the page can give while the engine
                # blocks. Detailed progress is in the terminal.
                turn = asyncio.run(
                    st.session_state.conversation.send(prompt)
                )

            except Exception as error:
                st.error(f"Something went wrong: {error}")
                st.stop()

        st.markdown(turn.reply)

        if turn.ungrounded:
            st.warning(
                f"No filings on file for {', '.join(turn.ungrounded)} — "
                f"their fundamentals could not be grounded in source "
                f"documents, so treat conviction on those names as lower."
            )

        report = None

        if turn.recommendation is not None and turn.request is not None:

            report = render_recommendation(turn.recommendation, turn.request)

            st.markdown(report)

        st.session_state.history.append(
            {
                "role": "assistant",
                "content": turn.reply,
                "report": report,
            }
        )
