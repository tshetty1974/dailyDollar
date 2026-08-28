import asyncio

from orchestration.investment_orchestrator import workflow


async def main():

    ticker = "NVDA"

    print("\n>>> STARTING MAGENTIC ORCHESTRATION\n")

    task = f"""
Conduct a complete investment research analysis of {ticker}.

Follow the research workflow defined by the manager.

Start with:
1. Fundamentals
2. Technical
3. News & Sentiment

Only after those Phase 1 analyses are complete, proceed to:
4. Macro / Thesis

Only after Macro / Thesis is complete, proceed to:
5. Risk

Finally, synthesize all findings.
"""

    result = await workflow.run(task)

    print("\n")
    print("=" * 70)
    print("ORCHESTRATION EVENTS")
    print("=" * 70)

    for event in result:
        event_type = getattr(event, "type", None)

        if event_type == "superstep_started":
            print(
                f"\n--- SUPERSTEP STARTED "
                f"(iteration={event.iteration}) ---"
            )

        elif event_type == "superstep_completed":
            print(
                f"--- SUPERSTEP COMPLETED "
                f"(iteration={event.iteration}) ---"
            )

        elif event_type == "group_chat":
            data = event.data

            participant_name = getattr(
                data,
                "participant_name",
                None,
            )

            if participant_name:
                print(
                    f"   >>> MANAGER DELEGATED TO: "
                    f"{participant_name}"
                )

        elif event_type == "executor_invoked":
            executor_id = event.executor_id

            if executor_id != "magentic_orchestrator":
                print(
                    f"   >>> AGENT INVOKED: "
                    f"{executor_id}"
                )

        elif event_type == "executor_completed":
            executor_id = event.executor_id

            if executor_id != "magentic_orchestrator":
                print(
                    f"   <<< AGENT COMPLETED: "
                    f"{executor_id}"
                )

        elif event_type == "output":
            print("\n>>> FINAL OUTPUT RECEIVED")

            print(event.data)

    print("\n>>> FINISHED MAGENTIC ORCHESTRATION")


if __name__ == "__main__":
    asyncio.run(main())