"""
Which companies this system can honestly analyse.

Requirement 3.5 says factual claims must be grounded in retrieved
source documents. That puts a hard boundary on the candidate universe:
we can only ground fundamentals for companies whose filings have been
ingested into the vector store. Anything outside that list can still be
analysed on price, news and macro, but its fundamentals would be the
model's recollection rather than evidence -- which is exactly what the
requirement forbids.

So the universe is derived from what is actually on disk rather than
hardcoded, and it cannot drift out of step with the ingest.
"""

from pathlib import Path


SEC_DIR = Path("data/sec")


def available_tickers() -> list[str]:
    """Tickers whose SEC filings have been ingested."""

    if not SEC_DIR.exists():
        return []

    tickers = {
        path.name.split("_")[0].upper()
        for path in SEC_DIR.glob("*.json")
    }

    return sorted(tickers)


def is_grounded(ticker: str) -> bool:
    """True when we hold filings for this ticker."""

    return ticker.upper().strip() in set(available_tickers())


def split_by_grounding(tickers: list[str]) -> tuple[list[str], list[str]]:
    """
    Split candidates into those we can ground and those we cannot.

    Returns (grounded, ungrounded). Ungrounded tickers are not rejected
    -- the technical, news and macro analysts work on any listed company
    -- but the caller is expected to say so, and the recommendation
    should carry lower conviction as a result.
    """

    known = set(available_tickers())

    grounded = []
    ungrounded = []

    for ticker in tickers:

        symbol = ticker.upper().strip()

        if symbol in known:
            grounded.append(symbol)
        else:
            ungrounded.append(symbol)

    return grounded, ungrounded
