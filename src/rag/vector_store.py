import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from processor import process_filing


DATA_DIR = Path("data/sec")
CHROMA_DIR = Path("data/chroma")

COLLECTION_NAME = "sec_filings"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def get_embedding_model():
    """
    Load the local embedding model.
    """

    print(
        f"Loading embedding model: {EMBEDDING_MODEL}"
    )

    return SentenceTransformer(
        EMBEDDING_MODEL
    )


def get_collection():
    """
    Create or load the Chroma collection.
    """

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR)
    )

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME
    )

    return collection


def process_all_filings():
    """
    Process every SEC HTML filing in data/sec/.
    """

    html_files = sorted(
        DATA_DIR.glob("*.html")
    )

    if not html_files:
        raise FileNotFoundError(
            "No SEC HTML files found."
        )

    all_chunks = []

    for html_path in html_files:

        print(
            f"\nProcessing: {html_path.name}"
        )

        chunks = process_filing(
            html_path
        )

        print(
            f"Chunks: {len(chunks)}"
        )

        all_chunks.extend(
            chunks
        )

    print(
        f"\nTotal chunks: {len(all_chunks)}"
    )

    return all_chunks


def add_chunks_to_chroma(
    chunks,
    collection,
    embedding_model,
):
    """
    Embed chunks and store them in Chroma.
    """

    # Chroma accepts batches, so we don't want to
    # send thousands of chunks at once.
    batch_size = 100

    for start in range(
        0,
        len(chunks),
        batch_size,
    ):

        batch = chunks[
            start:start + batch_size
        ]

        texts = [
            chunk["text"]
            for chunk in batch
        ]

        ids = [
            chunk["id"]
            for chunk in batch
        ]

        metadatas = [
            chunk["metadata"]
            for chunk in batch
        ]

        print(
            f"Embedding chunks "
            f"{start} - "
            f"{start + len(batch)} "
            f"/ {len(chunks)}"
        )

        embeddings = embedding_model.encode(
            texts,
            show_progress_bar=False,
        )

        embeddings = embeddings.tolist()

        collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    print(
        "\nFinished storing chunks in Chroma."
    )


def main():

    print("=" * 60)
    print("SEC RAG INGESTION")
    print("=" * 60)

    embedding_model = (
        get_embedding_model()
    )

    collection = get_collection()

    chunks = process_all_filings()

    add_chunks_to_chroma(
        chunks,
        collection,
        embedding_model,
    )

    print("\n" + "=" * 60)
    print("CHROMA STATUS")
    print("=" * 60)

    print(
        f"Collection: {COLLECTION_NAME}"
    )

    print(
        f"Documents stored: "
        f"{collection.count()}"
    )


if __name__ == "__main__":
    main()