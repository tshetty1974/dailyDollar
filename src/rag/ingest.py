import json
from pathlib import Path

import requests

SEC_USER_AGENT = "dailyDollar research project tavishishetty@yahoo.com"


COMPANIES = {
    # Mega-cap technology
    "NVDA": {
        "name": "NVIDIA",
        "cik": "0001045810",
        "annual_report_form": "10-K",
    },
    "MSFT": {
        "name": "Microsoft",
        "cik": "0000789019",
        "annual_report_form": "10-K",
    },
    "GOOGL": {
        "name": "Alphabet",
        "cik": "0001652044",
        "annual_report_form": "10-K",
    },
    "AMZN": {
        "name": "Amazon",
        "cik": "0001018724",
        "annual_report_form": "10-K",
    },
    "META": {
        "name": "Meta Platforms",
        "cik": "0001326801",
        "annual_report_form": "10-K",
    },
    "AAPL": {
        "name": "Apple",
        "cik": "0000320193",
        "annual_report_form": "10-K",
    },

    # Semiconductors / infrastructure
    "AVGO": {
        "name": "Broadcom",
        "cik": "0001730168",
        "annual_report_form": "10-K",
    },
    "AMD": {
        "name": "Advanced Micro Devices",
        "cik": "0000002488",
        "annual_report_form": "10-K",
    },
    "TSM": {
        "name": "Taiwan Semiconductor Manufacturing",
        "cik": "0001046179",
        "annual_report_form": "20-F",
    },
    "QCOM": {
        "name": "Qualcomm",
        "cik": "0000804328",
        "annual_report_form": "10-K",
    },
    "MU": {
        "name": "Micron Technology",
        "cik": "0000723125",
        "annual_report_form": "10-K",
    },

    # Enterprise / software
    "ORCL": {
        "name": "Oracle",
        "cik": "0001341439",
        "annual_report_form": "10-K",
    },
    "CRM": {
        "name": "Salesforce",
        "cik": "0001108524",
        "annual_report_form": "10-K",
    },
    "ADBE": {
        "name": "Adobe",
        "cik": "0000796343",
        "annual_report_form": "10-K",
    },
    "NOW": {
        "name": "ServiceNow",
        "cik": "0001373715",
        "annual_report_form": "10-K",
    },

    # Higher-growth / higher-risk
    "PLTR": {
        "name": "Palantir Technologies",
        "cik": "0001321655",
        "annual_report_form": "10-K",
    },
    "TSLA": {
        "name": "Tesla",
        "cik": "0001318605",
        "annual_report_form": "10-K",
    },
    "SNOW": {
        "name": "Snowflake",
        "cik": "0001640147",
        "annual_report_form": "10-K",
    },
    "CRWD": {
        "name": "CrowdStrike",
        "cik": "0001535527",
        "annual_report_form": "10-K",
    },
    "NFLX": {
        "name": "Netflix",
        "cik": "0001065280",
        "annual_report_form": "10-K",
    },
}


DATA_DIR = Path("data/sec")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_latest_annual_report(ticker: str):
    """
    Find the latest annual report for a company.

    For most US companies this is a 10-K.
    For foreign private issuers such as TSM, this is a 20-F.
    """

    if ticker not in COMPANIES:
        raise ValueError(f"Unknown ticker: {ticker}")

    company = COMPANIES[ticker]

    cik = company["cik"]
    expected_form = company["annual_report_form"]

    url = (
        f"https://data.sec.gov/submissions/"
        f"CIK{cik}.json"
    )

    headers = {
        "User-Agent": SEC_USER_AGENT
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    recent = data["filings"]["recent"]

    for i, form in enumerate(recent["form"]):

        if form == expected_form:

            return {
                "ticker": ticker,
                "company": company["name"],
                "filing_type": form,
                "filing_date": recent["filingDate"][i],
                "accession_number": recent["accessionNumber"][i],
                "primary_document": recent["primaryDocument"][i],
            }

    raise RuntimeError(
        f"No {expected_form} filing found for {ticker}"
    )


# ---------------------------------------------------------
# Download filing
# ---------------------------------------------------------

def download_filing(metadata):
    """
    Download the SEC filing HTML document
    and save its metadata alongside it.
    """

    ticker = metadata["ticker"]

    accession_number = (
        metadata["accession_number"]
        .replace("-", "")
    )

    cik = COMPANIES[ticker]["cik"]

    document = metadata["primary_document"]

    filing_type = metadata["filing_type"]

    # SEC Archives URL
    url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik)}/"
        f"{accession_number}/"
        f"{document}"
    )

    headers = {
        "User-Agent": SEC_USER_AGENT
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=60,
    )

    response.raise_for_status()

    # Example:
    # NVDA_2026-02-25_10-K.html
    output_filename = (
        f"{ticker}_"
        f"{metadata['filing_date']}_"
        f"{filing_type}.html"
    )

    output_path = DATA_DIR / output_filename

    output_path.write_text(
        response.text,
        encoding="utf-8",
    )

    # Save metadata separately.
    metadata_filename = (
        f"{ticker}_"
        f"{metadata['filing_date']}_"
        f"{filing_type}.json"
    )

    metadata_path = DATA_DIR / metadata_filename

    metadata_path.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Downloaded: {ticker}")
    print(f"Company: {metadata['company']}")
    print(f"Filing: {filing_type}")
    print(f"Filing date: {metadata['filing_date']}")
    print(f"Saved to: {output_path}")


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

if __name__ == "__main__":

    successful = 0
    failed = 0

    print(
        f"Starting SEC ingestion for "
        f"{len(COMPANIES)} companies..."
    )

    for ticker in COMPANIES:

        print("\n" + "=" * 60)
        print(f"Processing {ticker}")
        print("=" * 60)

        try:

            metadata = get_latest_annual_report(ticker)

            print(
                f"Found {metadata['filing_type']}: "
                f"{metadata['filing_date']}"
            )

            download_filing(metadata)

            successful += 1

        except Exception as e:

            failed += 1

            print(f"FAILED: {ticker}")
            print(f"Error: {e}")

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print("\n" + "=" * 60)
    print("INGESTION COMPLETE")
    print("=" * 60)

    print(f"Successful: {successful}")
    print(f"Failed:     {failed}")
    print(f"Total:      {len(COMPANIES)}")