from tools.news_tools import search_news


def main():

    print("=" * 60)
    print("NEWS TEST")
    print("=" * 60)

    result = search_news(
        ticker="AAPL",
        limit=5,
    )

    print(result)


if __name__ == "__main__":
    main()