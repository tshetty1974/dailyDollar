"""
Test 10 — is the Risk Analyst really usable from another runtime?

This script never imports the Risk Analyst. It knows only a URL. If it
gets a risk analysis back, the agent is genuinely operable across
runtimes rather than merely being a Python object with a wrapper.

Start the server first, in a separate terminal:
    PYTHONPATH=src python3 src/a2a_server.py

Then run this:
    PYTHONPATH=src python3 tests/test_a2a.py

Costs one model call, made by the server process.
"""

import asyncio
import sys

import httpx

try:
    from agent_framework_a2a import A2AAgent
except ImportError:  # pragma: no cover
    from agent_framework.a2a import A2AAgent


SERVER_URL = "http://127.0.0.1:9999"


# Deliberately a self-contained thesis rather than anything pulled from
# this project's own state: a remote caller would not have access to our
# findings, and the agent has to be useful without them.
THESIS = """
Pressure-test the following investment thesis.

NVIDIA is a buy at $227.98. It dominates AI accelerators, its CUDA
software ecosystem creates high switching costs, revenue reached
$130,497 million with free cash flow of $59,738 million, and demand for
AI infrastructure will continue growing for years. The stock trades
above its 50-day and 200-day moving averages, confirming the uptrend.

The investor is moderate risk with a 3-year horizon.
"""


async def main():

    # --- 1. discovery ------------------------------------------
    #
    # The agent card is how a caller learns what this agent does
    # without being told in advance. Fetching it first is what makes
    # this interoperability rather than a hardcoded integration.

    print("=" * 70)
    print("AGENT CARD (discovery)")
    print("=" * 70)

    try:
        async with httpx.AsyncClient(timeout=10) as client:

            card = await client.get(
                f"{SERVER_URL}/.well-known/agent-card.json"
            )

            print(card.text[:800])

    except Exception as error:
        print(f"could not fetch the agent card: {error}")
        print("\nIs the server running?")
        print("  PYTHONPATH=src python3 src/a2a_server.py")
        return

    # --- 2. use it like any other agent ------------------------
    #
    # A2AAgent wraps the remote agent so it satisfies the same
    # interface as a local one. Nothing below hints that the work is
    # happening in a different process.

    print("\n" + "=" * 70)
    print("CALLING THE REMOTE RISK ANALYST")
    print("=" * 70)

    remote_risk_analyst = A2AAgent(
        name="Risk Analyst (remote)",
        url=SERVER_URL,
    )

    response = await remote_risk_analyst.run(THESIS)

    text = getattr(response, "text", "") or ""

    print(text)

    # --- 3. checks ---------------------------------------------

    print("\n" + "=" * 70)
    print("CHECKS")
    print("=" * 70)

    print("got a response over A2A:", bool(text.strip()))

    print(
        "response reads as risk analysis:",
        any(
            word in text.lower()
            for word in ("risk", "downside", "assumption", "concentration")
        ),
    )

    # The strongest evidence available: the Risk Analyst's module was
    # never loaded in this interpreter. The work happened somewhere this
    # process has no access to beyond a URL.
    print(
        "the agent's module was never loaded here:",
        not any(name.startswith("agents.") for name in sys.modules),
    )


if __name__ == "__main__":
    asyncio.run(main())
