# utils/sec_policy_fetcher.py

import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from utils.logging_setup import logger
from utils.text_normalization import normalize_cash_in_lieu_phrases


class SECPolicyFetcher:
    BASE_URL = "https://efts.sec.gov/LATEST/search-index"
    HEADERS = {"User-Agent": "MyApp/1.0 (my.email@example.com)"}
    SEARCH_TERMS = [
        "reverse stock split",
        "no fractional shares",
        "reverse split",
        "in lieu",
        "preserve round lot",
    ]
    PREFERRED_FORMS = [
        "8-K",
        "DEF 14A",
        "PRE 14A",
        "S-1",
        "S-3",
        "S-4",
        "10-K",
        "10-Q",
    ]

    def __init__(self, back_days=30):
        self.start_date = (datetime.today() - timedelta(days=back_days)).strftime(
            "%Y-%m-%d"
        )
        self.end_date = datetime.today().strftime("%Y-%m-%d")

    def build_search_params(self, ticker):
        return {
            "q": f"{ticker} "
            + " OR ".join([f'"{term}"' for term in self.SEARCH_TERMS]),
            "dateRange": "custom",
            "startdt": self.start_date,
            "enddt": self.end_date,
            "category": "full",
            "start": 0,
            "count": 10,
        }

    def search_filings(self, ticker):
        try:
            logger.info(
                f"Searching SEC filings for {ticker} from {self.start_date} to {self.end_date}"
            )
            params = self.build_search_params(ticker)
            with requests.get(
                self.BASE_URL, params=params, headers=self.HEADERS, timeout=10
            ) as response:
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching SEC search results: {e}")
            return None

    def extract_policy_from_filing(self, filing_url):
        """Retrieve and classify fractional-share handling from a filing URL."""
        try:
            logger.info(f"Fetching and analyzing SEC filing from {filing_url}")
            with requests.get(filing_url, headers=self.HEADERS, timeout=10) as response:
                response.raise_for_status()
                html = response.text
            soup = BeautifulSoup(html, "html.parser")
            raw_text = soup.get_text(separator=" ")
            text_content = normalize_cash_in_lieu_phrases(raw_text).lower()

            policy_info = {
                "cash_in_lieu": "cash in lieu" in text_content
                or "paid in cash" in text_content,
                "round_up": "rounded up" in text_content and "cash" not in text_content,
                "round_down": "rounded down" in text_content,
            }

            return policy_info
        except Exception as e:
            logger.error(f"Error analyzing SEC filing text: {e}")
            return None

    def fetch_policy(self, ticker):
        search_data = self.search_filings(ticker)
        if not search_data or "hits" not in search_data.get("hits", {}):
            logger.warning(f"No filings found for ticker {ticker}")
            return None

        filings = search_data["hits"]["hits"]
        for filing in filings:
            form_type = filing["_source"].get("form", "")
            if form_type in ["8-K", "S-1", "S-3", "S-4", "14A", "10-K", "10-Q"]:
                cik = filing["_source"].get("ciks", [""])[0]
                accession_number = filing["_source"].get("adsh", "")
                file_id = filing["_id"].split(":")[1]
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number.replace('-', '')}/{file_id}"

                policy_info = self.extract_policy_from_filing(filing_url)
                if policy_info:
                    logger.info(f"Policy info extracted for {ticker}: {policy_info}")
                    return policy_info

        logger.warning(f"No valid policy extracted for {ticker}")
        return None

    def _extract_filing_url(self, filing):
        cik = filing["_source"].get("ciks", [""])[0]
        accession_number = filing["_source"].get("adsh", "")
        file_id = filing["_id"].split(":")[1]
        if not cik or not accession_number or not file_id:
            return None
        return (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
            f"{accession_number.replace('-', '')}/{file_id}"
        )

    def fetch_latest_filing_text(self, ticker):
        search_data = self.search_filings(ticker)
        if not search_data or "hits" not in search_data.get("hits", {}):
            logger.warning(f"No filings found for ticker {ticker}")
            return None

        filings = search_data["hits"]["hits"]
        if not filings:
            logger.warning(f"No filings returned for ticker {ticker}")
            return None
        prioritized = None
        for filing in filings:
            form_type = filing["_source"].get("form", "")
            if form_type in self.PREFERRED_FORMS:
                prioritized = filing
                break

        latest = prioritized or filings[0]
        filing_url = self._extract_filing_url(latest)
        if not filing_url:
            logger.warning("Unable to construct filing URL for %s", ticker)
            return None

        try:
            logger.info("Fetching latest SEC filing text from %s", filing_url)
            with requests.get(filing_url, headers=self.HEADERS, timeout=10) as response:
                response.raise_for_status()
                html = response.text
            soup = BeautifulSoup(html, "html.parser")
            raw_text = soup.get_text(separator=" ")
            text_content = normalize_cash_in_lieu_phrases(raw_text)
            return {"url": filing_url, "text": text_content}
        except Exception as e:
            logger.error("Error fetching latest SEC filing text: %s", e)
            return None
