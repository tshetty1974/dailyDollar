from rag.retriever import retrieve


def search_sec_filings(
    query: str,
    ticker: str,
) -> str:
    """
    Search SEC filings for evidence relevant to a financial
    research question.

    Args:
        query: Natural-language financial question.
        ticker: Stock ticker, e.g. NVDA.

    Returns:
        Relevant SEC filing excerpts with metadata.
    """

    results = retrieve(
        query=query,
        ticker=ticker,
        top_k=5,
    )

    documents = results.get(
        "documents",
        [[]],
    )[0]

    metadatas = results.get(
        "metadatas",
        [[]],
    )[0]

    distances = results.get(
        "distances",
        [[]],
    )[0]

    if not documents:
        return "No relevant SEC filing information was found."

    output = []

    for i, (document, metadata, distance) in enumerate(
        zip(documents, metadatas, distances),
        start=1,
    ):

        output.append(
            f"""
RESULT {i}

Company: {metadata.get("company")}
Ticker: {metadata.get("ticker")}
Filing: {metadata.get("filing_type")}
Date: {metadata.get("filing_date")}
Section: {metadata.get("section")}
Chunk: {metadata.get("chunk_index")}
Distance: {distance}

Text:
{document}
"""
        )

    return "\n".join(output)