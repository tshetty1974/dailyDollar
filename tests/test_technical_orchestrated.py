"""
Test 2 — does the Technical Analyst actually reach its MCP tools when it
runs as a Magentic participant?

This mirrors the real orchestrator:
  * tools bound at Agent construction (tools=[market_tool])
  * the MCP stdio session held open around workflow.run()

It uses a single-participant workflow so it costs a few model calls
rather than a full five-agent run.

Ground truth to compare against comes from Test 1. If the numbers below
match that output, the tool fired. If they do not, the agent is
hallucinating and the wiring is still wrong.

Run:  PYTHONPATH=src python3 tests/test_technical_orchestrated.py
"""

import asyncio
import os

from dotenv import load_dotenv

from agent_framework import Agent
from agent_framework.gemini import GeminiChatClient
from agent_framework.orchestrations import MagenticBuilder

from agents.technical import technical_agent, market_tool


load_dotenv()


manager_agent = Agent(
    client=GeminiChatClient(
        api_key=os.environ["GEMINI_API_KEY"],
        model="gemini-3.5-flash-lite",
    ),
    name="Manager",
    instructions=(
        "You coordinate a single Technical Analyst. Ask the Technical "
        "Analyst for NVDA's current price, its 50-day and 200-day "
        "moving averages, and its recent trend. As soon as the analyst "
        "answers with concrete numbers, the task is complete."
    ),
)


def final_text(events):
    """
    Pull the final answer out of the workflow event list.

    workflow.run() returns a list of WorkflowEvent objects, not a
    string. The finished answer lives on the event whose type is
    'output'. This is the same extraction the real orchestrator needs.
    """

    for event in events:

        if getattr(event, "type", None) == "output":

            text = getattr(
                getattr(event, "data", None),
                "text",
                None,
            )

            if text:
                return text

    return None


async def main():

    workflow = MagenticBuilder(
        participants=[technical_agent],
        manager_agent=manager_agent,
        max_round_count=3,
        max_stall_count=1,
    ).build()

    task = (
        "Report NVDA's current price, its 50-day and 200-day moving "
        "averages, and its recent trend. Use the market-data tools."
    )

    print(">>> RUNNING MAGENTIC WITH MCP SESSION HELD OPEN\n")

    async with market_tool:

        events = await workflow.run(task)

    print("\n" + "=" * 60)
    print("FINAL OUTPUT")
    print("=" * 60)

    answer = final_text(events)

    print(answer if answer else "(no output event found)")

    print("\n" + "=" * 60)
    print("EVENT TYPES SEEN")
    print("=" * 60)
    print([getattr(e, "type", "?") for e in events])


if __name__ == "__main__":
    asyncio.run(main())
