# utils/policy_resolver.py
"""Utilities for fetching and analyzing reverse split policy sources."""

import os
import requests
import re
from bs4 import BeautifulSoup
from utils.logging_setup import logger
from utils.sec_policy_fetcher import SECPolicyFetcher


class SplitPolicyResolver:
    NASDAQ_KEYWORDS = [
        "cash in lieu",
        "no fractional shares",
        "rounded up",
        "not issuing fractional shares",
    ]

    SEC_KEYWORDS = [
        "cash in lieu",
        "rounded up",
        "rounded down",
        "fractional shares will not be issued",
        "paid in cash",
    ]

    sec_fetcher = SECPolicyFetcher()

    @staticmethod
    def get_press_release_link_from_nasdaq(html_text):
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            link = soup.find("a", string="Press Release")
            if link and link.get("href"):
                press_url = link["href"]
                if press_url.startswith("/"):
                    press_url = "https://www.nasdaqtrader.com" + press_url
                logger.info(f"Press Release link found: {press_url}")
                return press_url
            else:
                logger.warning("No Press Release link found on NASDAQ page.")
                return None
        except Exception as e:
            logger.error(f"Error extracting Press Release link: {e}")
            return None

    @classmethod
    def get_sec_link_from_nasdaq(cls, nasdaq_url, ticker=None):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
            }
            response = requests.get(nasdaq_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            links = [
                link["href"]
                for link in soup.find_all("a", href=True)
                if any(
                    domain in link["href"].lower()
                    for domain in ["sec.gov", "quotemedia.com"]
                )
            ]

            if not links:
                text_link = soup.find("a", string=re.compile("SEC Filing", re.I))
                if text_link and text_link.get("href"):
                    links.append(text_link["href"])

            if not links:
                logger.warning("No SEC Filing links found on NASDAQ page.")
                return None

            # Prefer newer links or links associated with the correct ticker
            filtered_links = []
            for link in links:
                if "/rules/sro/" in link:
                    logger.info(f"Skipping rules/sro link: {link}")
                    continue

                if ticker and ticker.lower() in link.lower():
                    filtered_links.append(link)
                elif re.search(r"/20\d{2}/", link):
                    filtered_links.append(link)

            if filtered_links:
                sec_link = filtered_links[0]
                if sec_link.startswith("/"):
                    sec_link = "https://www.nasdaqtrader.com" + sec_link
                logger.info(f"SEC Filing link selected: {sec_link}")
                return sec_link

            logger.warning("No valid SEC Filing link after filtering.")
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve SEC link from NASDAQ: {e}")
            return None

    @staticmethod
    def fetch_sec_filing_text(sec_url):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
            }
            response = requests.get(sec_url, headers=headers, timeout=10)
            response.raise_for_status()

            if "html" in response.headers.get("Content-Type", ""):
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text(separator=" ")
            else:
                text = response.text

            text = " ".join(text.split())
            logger.info(f"Fetched SEC filing text ({len(text)} characters)")
            return text
        except Exception as e:
            logger.error(f"Error fetching SEC filing text: {e}")
            return None

    @staticmethod
    def fetch_body_text(url):
        """Retrieve cleaned body text from a webpage."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            body = soup.body or soup
            for tag in body(["script", "style"]):
                tag.decompose()
            text = body.get_text(separator=" ", strip=True)
            text = " ".join(text.split())
            logger.info(f"Fetched body text ({len(text)} characters) from {url}")
            return text
        except Exception as e:
            logger.error(f"Error fetching body text from {url}: {e}")
            return None

    @staticmethod
    def extract_round_up_snippet(text, window=5):
        """Return a short phrase around any round-up mention."""
        phrases = [
            "rounded up",
            "round up",
            "rounded to the nearest",
        ]
        for phrase in phrases:
            pattern = re.compile(
                rf'(?:\S+\s+){{0,{window}}}{re.escape(phrase)}(?:\s+\S+){{0,{window}}}',
                re.IGNORECASE,
            )
            match = pattern.search(text)
            if match:
                return match.group(0).strip()
        return None

    @staticmethod
    def log_full_return(url, text, log_file="volumes/logs/source_return.log"):
        """Append fetched text to a log file for reference."""
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"URL: {url}\n{text}\n\n")
        except Exception as e:
            logger.error(f"Failed to write full return to {log_file}: {e}")

    @staticmethod
    def analyze_fractional_share_policy(text):
        if not text:
            return "No text content available."

        text_lower = text.lower()

        if "fractional share" not in text_lower:
            return "No mention of fractional shares."

        if "cash in lieu" in text_lower or "paid in cash" in text_lower:
            return "Fractional shares will be paid out in cash."

        if "rounded up" in text_lower and not (
            "cash" in text_lower or "cash in lieu" in text_lower
        ):
            return "Fractional shares will be rounded up to a full share."

        if "rounded down" in text_lower:
            return "Fractional shares will be rounded down (likely forfeited)."

        return "Fractional share handling mentioned, but unclear policy."

    @classmethod
    def analyze_nasdaq_notice(cls, nasdaq_url, ticker=None):
        try:
            logger.info(f"Analyzing NASDAQ notice at {nasdaq_url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
            }
            response = requests.get(nasdaq_url, headers=headers, timeout=10)
            response.raise_for_status()

            text = response.text.lower()
            policy = cls.detect_policy_from_text(text, cls.NASDAQ_KEYWORDS)
            sec_url = cls.get_sec_link_from_nasdaq(nasdaq_url, ticker=ticker)
            press_url = cls.get_press_release_link_from_nasdaq(response.text)

            return {
                "policy": policy,
                "nasdaq_url": nasdaq_url,
                "sec_url": sec_url,
                "press_url": press_url,
            }
        except Exception as e:
            logger.error(f"Error analyzing NASDAQ notice: {e}")
            return None

    @classmethod
    def analyze_sec_filing(cls, sec_url):
        try:
            logger.info(f"Analyzing SEC filing at {sec_url}")
            filing_text = cls.fetch_sec_filing_text(sec_url)
            if filing_text:
                sec_policy = cls.analyze_fractional_share_policy(filing_text)
                snippet = cls.extract_round_up_snippet(filing_text)
                return {
                    "sec_policy": sec_policy,
                    "sec_url": sec_url,
                    "snippet": snippet,
                    "round_up_confirmed": bool(snippet),
                }
            else:
                return {
                    "sec_policy": "Unable to retrieve SEC filing.",
                    "sec_url": sec_url,
                }
        except Exception as e:
            logger.error(f"Failed to retrieve or analyze SEC filing: {e}")
            return {
                "sec_policy": "Unable to retrieve SEC filing.",
                "sec_url": sec_url,
            }

    @staticmethod
    def detect_policy_from_text(text, keywords):
        for keyword in keywords:
            if keyword in text:
                logger.info(f"Detected policy keyword: {keyword}")
                return keyword.capitalize()
        logger.warning("No specific policy keywords detected.")
        return "Policy not clearly stated."

    @classmethod
    def full_analysis(cls, nasdaq_url):
        try:
            logger.info(f"Starting full_analysis for: {nasdaq_url}")
            ticker = cls.extract_ticker_from_url(nasdaq_url)
            nasdaq_result = cls.analyze_nasdaq_notice(nasdaq_url, ticker=ticker)
            if not nasdaq_result:
                logger.warning("NASDAQ notice analysis failed or returned no result.")
                return None

            if nasdaq_result.get("sec_url"):
                sec_result = cls.analyze_sec_filing(nasdaq_result["sec_url"])
                nasdaq_result.update(sec_result)

            # Press Release fallback if SEC failed
            if (
                not nasdaq_result.get("sec_policy")
                or nasdaq_result["sec_policy"] == "Unable to retrieve SEC filing."
            ):
                press_url = nasdaq_result.get("press_url")
                if press_url:
                    logger.info(
                        f"Attempting fallback analysis using Press Release at {press_url}"
                    )
                    press_text = cls.fetch_sec_filing_text(press_url)
                    if press_text:
                        press_policy = cls.analyze_fractional_share_policy(press_text)
                        nasdaq_result["sec_policy"] = press_policy
                        logger.info(f"Press Release analysis result: {press_policy}")
                    else:
                        logger.warning(
                            "Failed to fetch Press Release text for policy analysis."
                        )

            # SEC Policy Fallback Search if no good info
            if not nasdaq_result.get("sec_policy") or nasdaq_result["sec_policy"] in [
                "Unable to retrieve SEC filing.",
                "No text content available.",
                "Policy not clearly stated.",
            ]:
                if ticker:
                    logger.info(
                        f"Attempting SECPolicyFetcher fallback for ticker: {ticker}"
                    )
                    fallback_policy = cls.sec_fetcher.fetch_policy(ticker)
                    if fallback_policy:
                        nasdaq_result.update(fallback_policy)

                        # Round-Up Check
                        policy_text = nasdaq_result.get(
                            "sec_policy"
                        ) or nasdaq_result.get("policy")
                        nasdaq_result["round_up_confirmed"] = cls.is_round_up_policy(
                            policy_text
                        )

            source_url = nasdaq_result.get("press_url") or nasdaq_result.get("sec_url")
            if source_url:
                body_text = cls.fetch_body_text(source_url)
                if body_text:
                    cls.log_full_return(source_url, body_text)
                    nasdaq_result["body_text"] = body_text
                else:
                    logger.warning(f"Failed to fetch body text from {source_url}")
            else:
                logger.warning("No press or SEC URL found for body text retrieval.")

            logger.info(f"Completed full_analysis for: {nasdaq_url}")
            return nasdaq_result

        except Exception as e:
            logger.error(f"Critical failure during full_analysis: {e}")
            return None

    @staticmethod
    def is_round_up_policy(text):
        """
        Determines if text confirms a round-up policy without disqualifying phrases.
        """
        if not text:
            return False

        text = text.lower()
        if "round up" in text and not any(
            bad_phrase in text
            for bad_phrase in [
                "no fractional",
                "sold",
                "aggregated",
                "not issued",
                "round down",
            ]
        ):
            return True

        return False

    @staticmethod
    def extract_ticker_from_url(url):
        match = re.search(r"\((.*?)\)", url)
        if match:
            return match.group(1)
        return None
