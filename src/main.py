"""
Terminal front end for the investment research system.

Deliberately thin: everything of substance lives in conversation.py, so
a web front end would be the same size and share the same engine.

Run:
    PYTHONPATH=src python3 src/main.py

Options:
    --trace          stream span timings to the terminal as they happen
    --user <id>      talk as a different user (memory is per user)
"""

import argparse
import asyncio
import sys

from observability import print_report, setup_observability


parser = argparse.ArgumentParser(description="Investment research assistant")
parser.add_argument("--trace", action="store_true", help="stream spans live")
parser.add_argument("--user", default="default", help="user id for memory")
args = parser.parse_args()

setup_observability(live=args.trace)

from conversation import Conversation  
from universe import available_tickers  


BANNER = """
======================================================================
  INVESTMENT RESEARCH ASSISTANT
======================================================================
  A team of specialist analysts researches each candidate, argues
  about it, and returns a recommendation with a suggested allocation.

  Just talk normally. For example:
    "I have 50k, fairly cautious, 5 years out. What about NVDA and AMD?"
    "why only 30% in NVDA?"

  Companies with filings on file ({count}):
  {universe}

  Type 'quit' to exit.
======================================================================
"""


async def main():

    print(
        BANNER.format(
            count=len(available_tickers()),
            universe=", ".join(available_tickers()),
        )
    )

    conversation = Conversation(user_id=args.user)

    while True:

        try:
            message = input("\nyou> ").strip()

        except (EOFError, KeyboardInterrupt):
            print("\n\nbye.")
            break

        if not message:
            continue

        if message.lower() in {"quit", "exit", "q"}:
            print("\nbye.")
            break

        try:
            turn = await conversation.send(message)

        except Exception as error:
            # A failed turn should not end the conversation: the user
            # can rephrase, and any completed research is checkpointed.
            print(f"\nsomething went wrong: {error}")
            continue

        print(f"\nassistant> {turn.reply}")

        if turn.ungrounded:
            print(
                f"\n  note: no filings on file for "
                f"{', '.join(turn.ungrounded)} — their fundamentals could "
                f"not be grounded in source documents, so conviction on "
                f"those names should be read as lower."
            )

        if turn.recommendation is None:
            continue

        # An analysis ran. Show the report, then the cost and latency
        # breakdown for the work that produced it.
        print("\n" + turn.recommendation.render(turn.request))

        print_report()


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        sys.exit(0)
