import yfinance as yf
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("market-data")


def _load_history(ticker: str, period: str):
    """
    Fetch price history with incomplete bars removed.

    An in-progress session is returned by the data provider with a NaN
    close. Left in place it corrupts the latest price and every
    trailing return, so those rows are dropped before any calculation.
    """

    history = yf.Ticker(ticker).history(period=period)

    if history.empty:
        return history

    return history.dropna(subset=["Close"])


@mcp.tool()
def get_stock_price(ticker: str) -> dict:
    """
    Get the latest available stock price and basic market information.

    Args:
        ticker: Stock ticker symbol, e.g. NVDA.
    """

    ticker = ticker.upper().strip()

    history = _load_history(ticker, "5d")

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

    history = _load_history(ticker, period)

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


@mcp.tool()
def get_technical_indicators(
    ticker: str,
    period: str = "1y",
) -> dict:
    """
    Get computed technical indicators for a stock.

    Returns derived statistics (moving averages, returns, volatility,
    drawdown, 52-week range, volume trend) so that the analyst does not
    have to do arithmetic over raw price history.

    Args:
        ticker: Stock ticker symbol, e.g. NVDA.
        period: Historical period such as 3mo, 6mo, 1y, 2y, 5y.
    """

    ticker = ticker.upper().strip()

    history = _load_history(ticker, period)

    if history.empty:
        return {
            "error": f"No market data found for {ticker}"
        }

    closes = history["Close"]
    volumes = history["Volume"]

    latest_close = float(closes.iloc[-1])

    def sma(window: int):
        """Simple moving average, or None if not enough history."""

        if len(closes) < window:
            return None

        return round(
            float(closes.tail(window).mean()),
            2,
        )

    def trailing_return(days: int):
        """Percent return over the last N trading days."""

        if len(closes) <= days:
            return None

        past = float(closes.iloc[-(days + 1)])

        if not past:
            return None

        return round(
            ((latest_close - past) / past) * 100,
            2,
        )

    # Annualised volatility from daily percent changes.
    daily_returns = closes.pct_change().dropna()

    if len(daily_returns) > 1:
        annualised_volatility = round(
            float(daily_returns.std()) * (252 ** 0.5) * 100,
            2,
        )
    else:
        annualised_volatility = None

    # Maximum peak-to-trough decline over the period.
    running_peak = closes.cummax()
    drawdowns = (closes - running_peak) / running_peak

    max_drawdown = round(
        float(drawdowns.min()) * 100,
        2,
    )

    # Compare recent volume against the full-period average
    # to describe whether activity is picking up.
    average_volume = float(volumes.mean())

    recent_volume = float(volumes.tail(20).mean())

    volume_change_percent = (
        round(
            ((recent_volume - average_volume) / average_volume) * 100,
            2,
        )
        if average_volume
        else None
    )

    return {
        "ticker": ticker,
        "period": period,
        "as_of": str(history.index[-1].date()),
        "data_points": len(closes),

        "latest_close": round(latest_close, 2),

        "sma_20": sma(20),
        "sma_50": sma(50),
        "sma_200": sma(200),

        "return_1m_percent": trailing_return(21),
        "return_3m_percent": trailing_return(63),
        "return_6m_percent": trailing_return(126),
        "return_1y_percent": trailing_return(252),

        "period_high": round(float(closes.max()), 2),
        "period_low": round(float(closes.min()), 2),

        "annualised_volatility_percent": annualised_volatility,
        "max_drawdown_percent": max_drawdown,

        "average_daily_volume": int(average_volume),
        "recent_20d_average_volume": int(recent_volume),
        "volume_change_percent": volume_change_percent,
    }


if __name__ == "__main__":
    mcp.run()