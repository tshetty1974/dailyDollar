import os
import requests

from bs4 import BeautifulSoup
from dotenv import load_dotenv


load_dotenv()


MARKETAUX_URL = (
    "https://api.marketaux.com/v1/news/all"
)

MIN_MATCH_SCORE = 20


def fetch_article_text(url: str) -> str:
    """
    Try to retrieve readable text from an article URL.

    This is best-effort. Some publishers may block
    automated requests, use JavaScript, or require
    a subscription.
    """

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; DailyDollar/1.0)"
                )
            },
            timeout=10,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        # Remove elements that are unlikely to contain
        # article content.
        for tag in soup.find_all(
            [
                "script",
                "style",
                "noscript",
                "svg",
                "nav",
                "footer",
                "header",
            ]
        ):
            tag.decompose()

        text = soup.get_text(
            " ",
            strip=True,
        )

        return text

    except Exception:
        return ""


def search_news(
    ticker: str,
    limit: int = 10,
) -> str:
    """
    Retrieve relevant recent news for a ticker.

    Process:

        Marketaux
            ↓
        Recent candidates
            ↓
        Match-score filtering
            ↓
        Article content enrichment
            ↓
        Return news evidence
    """

    api_token = os.environ[
        "MARKETAUX_API_TOKEN"
    ]

    ticker = ticker.upper()

    # --------------------------------------------------
    # Retrieve a candidate pool.
    #
    # We ask for more candidates than we ultimately
    # return because some may fail the relevance check.
    # --------------------------------------------------

    candidate_limit = 10

    params = {
        "api_token": api_token,
        "symbols": ticker,

        "filter_entities": "true",
        "must_have_entities": "true",
        "group_similar": "true",

        "language": "en",

        # Latest news first.
        "sort": "published_at",

        "limit": candidate_limit,
    }

    response = requests.get(
        MARKETAUX_URL,
        params=params,
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    # --------------------------------------------------
    # API errors
    # --------------------------------------------------

    if "error" in data:

        return (
            "News retrieval failed: "
            f"{data['error']}"
        )

    articles = data.get(
        "data",
        [],
    )

    if not articles:

        return (
            f"No recent news was found for "
            f"{ticker}."
        )

    # --------------------------------------------------
    # Filter articles by ticker relevance.
    # --------------------------------------------------

    relevant_articles = []

    for article in articles:

        ticker_entity = None

        for entity in article.get(
            "entities",
            [],
        ):

            if (
                entity.get("symbol", "")
                .upper()
                == ticker
            ):
                ticker_entity = entity
                break

        # If Marketaux cannot associate the article
        # with our ticker, don't pass it to the agent.
        if ticker_entity is None:
            continue

        match_score = ticker_entity.get(
            "match_score"
        )

        # Reject clearly unrelated articles.
        if (
            match_score is not None
            and match_score < MIN_MATCH_SCORE
        ):
            continue

        relevant_articles.append(
            {
                "ticker": ticker,

                "title": article.get(
                    "title"
                ),

                "source": article.get(
                    "source"
                ),

                "published_at": article.get(
                    "published_at"
                ),

                "description": article.get(
                    "description"
                ),

                "snippet": article.get(
                    "snippet"
                ),

                "url": article.get(
                    "url"
                ),

                "sentiment_score": (
                    ticker_entity.get(
                        "sentiment_score"
                    )
                ),

                "match_score": match_score,
            }
        )

    # --------------------------------------------------
    # No sufficiently relevant news.
    # --------------------------------------------------

    if not relevant_articles:

        return (
            f"No sufficiently relevant recent "
            f"news was found for {ticker}."
        )

    # --------------------------------------------------
    # Fetch article content.
    #
    # This is best-effort. If the publisher blocks us,
    # we keep the Marketaux description/snippet.
    # --------------------------------------------------

    final_articles = []

    for article in relevant_articles[:limit]:

        url = article.get("url")

        article_text = ""

        if url:
            article_text = fetch_article_text(
                url
            )

        # Don't send enormous webpages to the LLM.
        if article_text:
            article_text = article_text[:12000]

        article["article_text"] = (
            article_text
            if article_text
            else None
        )

        final_articles.append(
            article
        )

    # --------------------------------------------------
    # Return evidence to the News Agent.
    # --------------------------------------------------

    return str(final_articles)