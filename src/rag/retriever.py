from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


CHROMA_DIR = Path("data/chroma")
COLLECTION_NAME = "sec_filings"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def get_collection():
    """Load the existing Chroma collection."""

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR)
    )

    return client.get_collection(
        name=COLLECTION_NAME
    )


_embedding_model = None


def get_embedding_model():
    """Load the embedding model once and reuse it."""

    global _embedding_model

    if _embedding_model is None:
        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL
        )

    return _embedding_model


def retrieve(
    query: str,
    ticker: str | None = None,
    top_k: int = 5,
):
    """
    Retrieve the most relevant SEC filing chunks.

    Args:
        query: Natural-language question.
        ticker: Optional ticker filter.
        top_k: Number of chunks to retrieve.
    """

    collection = get_collection()

    embedding_model = get_embedding_model()

    # Convert the user's question into the same
    # vector space as our document chunks.
    query_embedding = embedding_model.encode(
        query
    ).tolist()

    query_kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
    }

    # If a ticker is supplied, only search that company's
    # filings.
    if ticker:
        query_kwargs["where"] = {
            "ticker": ticker.upper()
        }

    results = collection.query(
        **query_kwargs
    )

    return results


def print_results(results):
    """Pretty-print retrieved chunks."""

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    print("=" * 70)
    print("RETRIEVAL RESULTS")
    print("=" * 70)

    for i, (document, metadata, distance) in enumerate(
        zip(documents, metadatas, distances),
        start=1,
    ):

        print("\n" + "-" * 70)
        print(f"RESULT {i}")
        print("-" * 70)

        print(f"Distance: {distance}")

        print("\nMetadata:")
        print(f"Ticker:      {metadata.get('ticker')}")
        print(f"Company:     {metadata.get('company')}")
        print(f"Filing:      {metadata.get('filing_type')}")
        print(f"Date:        {metadata.get('filing_date')}")
        print(f"Section:     {metadata.get('section')}")
        print(
            f"Chunk:       {metadata.get('chunk_index')}"
        )

        print("\nText:")
        print(document)


def main():

    # Change this question to test different queries.
    query = (
        "What are NVIDIA's biggest supply "
        "chain risks?"
    )

    ticker = "NVDA"

    print(f"\nQuery: {query}")
    print(f"Ticker filter: {ticker}\n")

    results = retrieve(
        query=query,
        ticker=ticker,
        top_k=5,
    )

    print_results(results)


if __name__ == "__main__":
    main()