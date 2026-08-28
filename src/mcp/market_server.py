import yfinance as yf
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("market-data")


@mcp.tool()
def get_stock_price(ticker: str) -> dict:
    """
    Get the latest available stock price and basic market information.

    Args:
        ticker: Stock ticker symbol, e.g. NVDA.
    """

    ticker = ticker.upper().strip()

    stock = yf.Ticker(ticker)

    history = stock.history(period="5d")

    if history.empty:
        return {
            "error": f"No market data found for {ticker}"
        }

    latest = history.iloc[-1]

    price = float(latest["Close"])

    # A previous trading-day price is normally available
    # for established stocks.
    #
    # If it is not available, we return None rather than
    # incorrectly saying that the stock had 0 change.
    if len(history) > 1:

        previous_close = float(
            history.iloc[-2]["Close"]
        )

        change = price - previous_close

        change_percent = (
            (change / previous_close) * 100
            if previous_close
            else None
        )

    else:

        previous_close = None
        change = None
        change_percent = None

    return {
        "ticker": ticker,

        "price": round(price, 2),

        "previous_close": (
            round(previous_close, 2)
            if previous_close is not None
            else None
        ),

        "change": (
            round(change, 2)
            if change is not None
            else None
        ),

        "change_percent": (
            round(change_percent, 2)
            if change_percent is not None
            else None
        ),

        "date": str(
            history.index[-1].date()
        ),
    }


@mcp.tool()
def get_historical_prices(
    ticker: str,
    period: str = "1y",
) -> list[dict]:
    """
    Get historical daily stock prices.

    Args:
        ticker: Stock ticker symbol, e.g. NVDA.
        period: Historical period such as 1mo, 3mo, 6mo, 1y, 2y, 5y.
    """

    ticker = ticker.upper().strip()

    stock = yf.Ticker(ticker)

    history = stock.history(
        period=period
    )

    if history.empty:
        return [
            {
                "error": (
                    f"No market data found for {ticker}"
                )
            }
        ]

    results = []

    for date, row in history.iterrows():

        results.append(
            {
                "date": str(date.date()),

                "open": round(
                    float(row["Open"]),
                    2,
                ),

                "high": round(
                    float(row["High"]),
                    2,
                ),

                "low": round(
                    float(row["Low"]),
                    2,
                ),

                "close": round(
                    float(row["Close"]),
                    2,
                ),

                "volume": int(
                    row["Volume"]
                ),
            }
        )

    return results


if __name__ == "__main__":
    mcp.run()