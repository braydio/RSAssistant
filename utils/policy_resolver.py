# utils/policy_resolver.py
"""Utilities for fetching and analyzing reverse split policy sources."""

import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from utils.logging_setup import logger
from utils.sec_policy_fetcher import SECPolicyFetcher
from utils.config_utils import VOLUMES_DIR, PROGRAMMATIC_POLICY_ENABLED
from utils.text_normalization import normalize_cash_in_lieu_phrases
from utils.openai_utils import extract_reverse_split_details


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
    def _request_headers_for_url(url: str | None = None) -> dict:
        default_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
        )
        headers = {"User-Agent": default_ua}
        if url and "sec.gov" in url.lower():
            sec_ua = (
                os.getenv("SEC_REQUEST_USER_AGENT")
                or os.getenv("SEC_USER_AGENT")
                or "RSAssistant/3.1 (ops@example.com)"
            )
            headers["User-Agent"] = sec_ua
            sec_from = os.getenv("SEC_REQUEST_FROM") or os.getenv("SEC_FROM")
            if sec_from:
                headers["From"] = sec_from
        return headers

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
            with requests.get(nasdaq_url, headers=headers, timeout=10) as response:
                response.raise_for_status()
                html = response.text
            soup = BeautifulSoup(html, "html.parser")
            candidates = []
            seen = set()
            for link in soup.find_all("a", href=True):
                href = (link.get("href") or "").strip()
                if not href:
                    continue
                full_href = urljoin(nasdaq_url, href)
                href_lower = full_href.lower()
                text = " ".join(link.get_text(" ", strip=True).split())
                text_lower = text.lower()

                is_sec_domain = any(
                    domain in href_lower for domain in ["sec.gov", "quotemedia.com"]
                )
                is_sec_label = bool(
                    re.search(r"\bsec filing\b|\bform\s+\d", text_lower)
                )
                if not (is_sec_domain or is_sec_label):
                    continue

                if full_href in seen:
                    continue
                seen.add(full_href)
                candidates.append((full_href, text))

            if not candidates:
                logger.warning("No SEC Filing links found on NASDAQ page.")
                return None

            def _score(candidate: tuple[str, str]) -> int:
                link, text = candidate
                link_lower = link.lower()
                text_lower = text.lower()
                score = 0

                if "/rules/sro/" in link_lower:
                    # Rule filings are usually generic exchange docs, not issuer filings.
                    score -= 1000
                if re.fullmatch(r"https?://(?:www\.)?sec\.gov/?", link_lower):
                    # SEC homepage is not a filing link.
                    score -= 1000
                if "sec.gov/archives/edgar" in link_lower:
                    score += 120
                if "/ixviewer/" in link_lower:
                    score += 60
                if "quotemedia.com" in link_lower:
                    score += 25
                if "sec filing" in text_lower:
                    score += 40
                if re.search(r"\b(?:8-k|6-k|20-f|10-k|10-q)\b", f"{link_lower} {text_lower}"):
                    score += 35
                if ticker and (
                    ticker.lower() in link_lower or ticker.lower() in text_lower
                ):
                    score += 20
                if re.search(r"/20\d{2}/", link_lower):
                    score += 10
                return score

            scored = sorted(candidates, key=_score, reverse=True)
            sec_link, sec_text = scored[0]
            top_score = _score(scored[0])
            if top_score <= 0:
                logger.warning("No valid SEC Filing link after filtering.")
                return None

            logger.info(
                "SEC Filing link selected: %s (score=%s, label=%s, candidates=%s)",
                sec_link,
                top_score,
                sec_text or "N/A",
                len(candidates),
            )
            return sec_link

        except Exception as e:
            logger.error(f"Failed to retrieve SEC link from NASDAQ: {e}")
            return None

    @staticmethod
    def fetch_sec_filing_text(sec_url):
        try:
            headers = SplitPolicyResolver._request_headers_for_url(sec_url)
            with requests.get(sec_url, headers=headers, timeout=10) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                response_text = response.text

            if "html" in content_type:
                soup = BeautifulSoup(response_text, "html.parser")
                text = soup.get_text(separator=" ")
            else:
                text = response_text

            text = " ".join(text.split())
            logger.info(f"Fetched SEC filing text ({len(text)} characters)")
            return text
        except Exception as e:
            logger.error(f"Error fetching SEC filing text: {e}")
            return None

    @staticmethod
    def _extract_main_text(html_text: str) -> str:
        """Return the most relevant text block from an HTML document."""
        soup = BeautifulSoup(html_text, "html.parser")
        unwanted_attr = re.compile(
            r"(?<![a-z])(nav|menu|footer|header|sidebar|cookie|consent|subscribe|"
            r"promo|banner|advert|ads?|social|related|breadcrumb|search|modal|"
            r"popup|cta|hero)(?![a-z])",
            re.IGNORECASE,
        )
        for tag in soup(
            [
                "script",
                "style",
                "nav",
                "header",
                "footer",
                "aside",
                "form",
                "noscript",
                "svg",
                "canvas",
            ]
        ):
            tag.decompose()

        for tag in soup.find_all(True):
            if not tag or not isinstance(tag, Tag):
                continue
            try:
                class_list = tag.get("class") or []
                attr_text = " ".join(
                    filter(
                        None,
                        [
                            tag.get("id", ""),
                            " ".join(class_list),
                            tag.get("role", ""),
                        ],
                    )
                )
            except Exception:
                continue
            if attr_text and unwanted_attr.search(attr_text):
                tag.decompose()

        preferred_selectors = [
            "article",
            "main",
            "[itemprop='articleBody']",
            ".article-body",
            ".news-release-body",
            ".story-body",
        ]
        candidates = []
        for selector in preferred_selectors:
            for match in soup.select(selector):
                if match not in candidates:
                    candidates.append(match)
        for match in soup.find_all(["main", "article", "section", "div", "body"]):
            if match not in candidates:
                candidates.append(match)

        best_text = ""
        best_score = 0
        for candidate in candidates:
            text = candidate.get_text(separator=" ", strip=True)
            words = text.split()
            word_count = len(words)
            if word_count < 40:
                continue

            link_text = " ".join(
                link.get_text(separator=" ", strip=True)
                for link in candidate.find_all("a")
            )
            link_word_count = len(link_text.split())
            link_density = link_word_count / max(word_count, 1)

            bonus = 0
            if candidate.name in {"article", "main"}:
                bonus += 50
            classes = " ".join(candidate.get("class") or [])
            cid = candidate.get("id") or ""
            if re.search(r"article|story|body|content|release", f"{classes} {cid}", re.I):
                bonus += 25
            if re.search(r"press release|news release|investor", text, re.IGNORECASE):
                bonus += 20
            if re.search(r"reverse (?:stock )?split", text, re.IGNORECASE):
                bonus += 20

            score = word_count * (1 - min(link_density, 0.9)) + bonus
            if score > best_score:
                best_score = score
                best_text = text

        if not best_text:
            best_text = soup.get_text(separator=" ", strip=True)

        return " ".join(best_text.split())

    @staticmethod
    def _trim_to_context(text: str, ticker: str | None = None) -> str:
        if not text:
            return text

        lowered = text.lower()
        priorities = [
            "fractional",
            "fractional share",
            "fractional shares",
            "handling of fractional shares",
            "no fractional shares",
            "cash in lieu",
            "rounded up",
            "round up",
            "rounded to the nearest",
            "rounded up to the next whole number",
            "next whole number",
            "share consolidation",
            "stock consolidation",
            "reverse share split",
        ]
        triggers = [
            "reverse",
            "reverse stock split",
            "reverse split",
            "reverse share split",
            "share consolidation",
            "stock consolidation",
            "consolidation",
        ]

        start_idx = None

        for phrase in priorities:
            idx = lowered.find(phrase)
            if idx != -1:
                start_idx = idx if start_idx is None else min(start_idx, idx)

        if start_idx is None and ticker:
            idx = lowered.find(ticker.lower())
            if idx != -1:
                start_idx = idx

        if start_idx is None:
            for phrase in triggers:
                idx = lowered.find(phrase)
                if idx != -1:
                    start_idx = idx if start_idx is None else min(start_idx, idx)

        if start_idx is None:
            return text

        start_idx = max(0, start_idx - 120)
        # Avoid trimming deep into the article; we still want title/lead context
        # so the LLM sees what event is being discussed.
        start_idx = min(start_idx, 400)
        return text[start_idx:]

    @staticmethod
    def _needs_sec_fallback(
        text: str | None, ticker: str | None, min_length: int = 400
    ) -> bool:
        if not text:
            return True
        if len(text) < min_length:
            return True
        lowered = text.lower()
        triggers = ["reverse", "fractional", "shareholder"]
        if any(trigger in lowered for trigger in triggers):
            return False
        if ticker and ticker.lower() in lowered:
            return False
        return True

    @classmethod
    def fetch_body_text(cls, url, ticker: str | None = None):
        """Retrieve cleaned main body text from a webpage."""
        try:
            headers = cls._request_headers_for_url(url)
            response = None
            with requests.get(url, headers=headers, timeout=10) as response:
                response.raise_for_status()
                html = response.text or ""

            extracted = cls._extract_main_text(html)
            text = cls._trim_to_context(extracted, ticker=ticker)
            lowered = text.lower()
            logger.info(
                "Fetched body text (%s chars, extracted=%s chars, has_reverse=%s, has_fractional=%s) from %s",
                len(text),
                len(extracted),
                "reverse split" in lowered or "reverse stock split" in lowered,
                "fractional share" in lowered or "fractional shares" in lowered,
                url,
            )
            return text
        except Exception as e:
            snippet = ""
            try:
                snippet = (response.text or "")[:200].replace("\n", " ")
            except Exception:
                snippet = ""
            if snippet:
                logger.error(
                    "Body fetch failed for %s. HTML head snippet: %s",
                    url,
                    snippet,
                )
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
    def extract_effective_date(text):
        """Return the effective date (YYYY-MM-DD) if present in text."""
        if not text:
            return None

        patterns = [
            r"(?:effective|takes effect|will take effect|will be effective|becomes effective)[^\.\n]*?((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})",
            r"(?:effective|takes effect|will take effect|will be effective|becomes effective)[^\.\n]*?(\d{1,2}/\d{1,2}/\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1) if match.lastindex else match.group(0)
                for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"):
                    try:
                        return datetime.strptime(date_str, fmt).date().isoformat()
                    except ValueError:
                        continue
        return None

    @staticmethod
    def log_full_return(
        url,
        text,
        log_file=str(VOLUMES_DIR / "logs" / "source_return.log"),
    ):
        """Append fetched text to a log file for reference."""
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"URL: {url}\n{text}\n\n")
        except Exception as e:
            logger.error(f"Failed to write full return to {log_file}: {e}")

    @staticmethod
    def analyze_fractional_share_policy(text):
        """Summarize how fractional shares are handled in the provided text."""
        if not text:
            return "No text content available."

        text = normalize_cash_in_lieu_phrases(text)
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
        """Inspect a NASDAQ corporate action notice for fractional share policy."""
        try:
            logger.info(f"Analyzing NASDAQ notice at {nasdaq_url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
            }
            with requests.get(nasdaq_url, headers=headers, timeout=10) as response:
                response.raise_for_status()
                html = response.text

            normalized_text = normalize_cash_in_lieu_phrases(html).lower()
            policy = cls.detect_policy_from_text(normalized_text, cls.NASDAQ_KEYWORDS)
            sec_url = cls.get_sec_link_from_nasdaq(nasdaq_url, ticker=ticker)
            press_url = cls.get_press_release_link_from_nasdaq(html)

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
        """Parse an SEC filing for policy details and effective date."""
        try:
            logger.info(f"Analyzing SEC filing at {sec_url}")
            filing_text = cls.fetch_sec_filing_text(sec_url)
            if filing_text:
                sec_policy = cls.analyze_fractional_share_policy(filing_text)
                snippet = cls.extract_round_up_snippet(filing_text)
                effective_date = cls.extract_effective_date(filing_text)
                return {
                    "sec_policy": sec_policy,
                    "sec_url": sec_url,
                    "snippet": snippet,
                    "round_up_confirmed": bool(snippet),
                    "effective_date": effective_date,
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
        """Return the highest priority policy keyword detected in ``text``.

        The method normalizes text and then evaluates a priority-ordered set of
        policy phrases. Round-up confirmations are evaluated before "no
        fractional" language so that statements combining both are still
        classified as round-up outcomes.

        Args:
            text: Source text to inspect.
            keywords: Iterable of policy keywords to search for.

        Returns:
            A sentence-cased description of the detected policy, or an "unclear"
            message if no keywords were located.
        """

        normalized_text = normalize_cash_in_lieu_phrases(text).lower()

        prioritized_keywords = [
            "rounded up",
            "rounded down",
            "cash in lieu",
            "paid in cash",
            "cash equivalent",
            "no fractional shares",
            "not issuing fractional shares",
            "fractional shares will not be issued",
        ]

        # Prioritize critical confirmations regardless of the provided ordering.
        for keyword in prioritized_keywords:
            if keyword in keywords and keyword in normalized_text:
                logger.info(f"Detected policy keyword: {keyword}")
                return keyword.capitalize()

        # Fall back to the provided ordering if no priority keyword matched.
        for keyword in keywords:
            if keyword in normalized_text:
                logger.info(f"Detected policy keyword: {keyword}")
                return keyword.capitalize()

        logger.warning("No specific policy keywords detected.")
        return "Policy not clearly stated."

    @classmethod
    def full_analysis(cls, nasdaq_url, ticker_hint: str | None = None):
        """Gather policy info, effective date, and source text from NASDAQ notice."""
        try:
            logger.info(f"Starting full_analysis for: {nasdaq_url}")
            ticker = ticker_hint or cls.extract_ticker_from_url(nasdaq_url)
            if PROGRAMMATIC_POLICY_ENABLED:
                nasdaq_result = cls.analyze_nasdaq_notice(nasdaq_url, ticker=ticker)
            else:
                logger.info(
                    "Programmatic policy analysis disabled; using LLM parsing only."
                )
                nasdaq_result = {
                    "nasdaq_url": nasdaq_url,
                    "policy": "Programmatic policy parsing disabled.",
                    "sec_url": None,
                    "press_url": None,
                }
                # Even in LLM-only mode, discover better source links for context.
                # Nasdaq notices often contain Press Release / SEC links.
                if "nasdaqtrader.com/tradernews.aspx" in nasdaq_url.lower():
                    try:
                        headers = {
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/112.0.0.0 Safari/537.36"
                            )
                        }
                        with requests.get(
                            nasdaq_url, headers=headers, timeout=10
                        ) as response:
                            response.raise_for_status()
                            html = response.text or ""
                        nasdaq_result["press_url"] = cls.get_press_release_link_from_nasdaq(
                            html
                        )
                        nasdaq_result["sec_url"] = cls.get_sec_link_from_nasdaq(
                            nasdaq_url, ticker=ticker
                        )
                        logger.info(
                            "LLM-only mode link discovery for %s -> press_url=%s sec_url=%s",
                            nasdaq_url,
                            nasdaq_result.get("press_url"),
                            nasdaq_result.get("sec_url"),
                        )
                    except Exception as link_err:
                        logger.warning(
                            "LLM-only mode link discovery failed for %s: %s",
                            nasdaq_url,
                            link_err,
                        )
            if not nasdaq_result:
                logger.warning("NASDAQ notice analysis failed or returned no result.")
                return None

            if PROGRAMMATIC_POLICY_ENABLED and nasdaq_result.get("sec_url"):
                sec_result = cls.analyze_sec_filing(nasdaq_result["sec_url"])
                nasdaq_result.update(sec_result)

            # Press Release fallback if SEC failed
            if PROGRAMMATIC_POLICY_ENABLED and (
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
                        if not nasdaq_result.get("effective_date"):
                            nasdaq_result["effective_date"] = cls.extract_effective_date(
                                press_text
                            )
                        logger.info(f"Press Release analysis result: {press_policy}")
                    else:
                        logger.warning(
                            "Failed to fetch Press Release text for policy analysis."
                        )

            # SEC Policy Fallback Search if no good info
            if PROGRAMMATIC_POLICY_ENABLED:
                if not nasdaq_result.get("sec_policy") or nasdaq_result[
                    "sec_policy"
                ] in [
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

            source_url = nasdaq_result.get("sec_url") or nasdaq_result.get("press_url")
            if not source_url:
                logger.info(
                    "No press/SEC URL found; falling back to NASDAQ notice for body text."
                )
                source_url = nasdaq_url
            if source_url:
                body_text = cls.fetch_body_text(source_url, ticker=ticker)
                if not body_text and source_url != nasdaq_url:
                    logger.warning(
                        "Primary source fetch failed for %s; falling back to NASDAQ notice %s",
                        source_url,
                        nasdaq_url,
                    )
                    body_text = cls.fetch_body_text(nasdaq_url, ticker=ticker)
                    if body_text:
                        source_url = nasdaq_url
                if body_text:
                    cls.log_full_return(source_url, body_text)
                    nasdaq_result["body_text"] = body_text
                    if not nasdaq_result.get("effective_date"):
                        nasdaq_result["effective_date"] = cls.extract_effective_date(
                            body_text
                        )
                    if ticker and cls._needs_sec_fallback(body_text, ticker):
                        logger.info(
                            "Body text lacks key triggers; attempting SEC fallback for %s",
                            ticker,
                        )
                        sec_fallback = cls.sec_fetcher.fetch_latest_filing_text(
                            ticker
                        )
                        if sec_fallback:
                            body_text = sec_fallback["text"]
                            source_url = sec_fallback["url"]
                            nasdaq_result["body_text"] = body_text
                            nasdaq_result["sec_url"] = source_url
                    llm_details = extract_reverse_split_details(
                        body_text, source_url=source_url, ticker=ticker
                    )
                    if llm_details:
                        nasdaq_result["llm_details"] = llm_details
                        if llm_details.get("effective_date"):
                            nasdaq_result["effective_date"] = llm_details.get(
                                "effective_date"
                            )
                        if llm_details.get("split_ratio"):
                            nasdaq_result["split_ratio"] = llm_details.get(
                                "split_ratio"
                            )
                        if llm_details.get("reverse_split_confirmed") is not None:
                            nasdaq_result["reverse_split_confirmed"] = llm_details.get(
                                "reverse_split_confirmed"
                            )
                        policy = llm_details.get("fractional_share_policy")
                        if policy:
                            nasdaq_result["fractional_share_policy"] = policy
                            llm_round_up = policy in {
                                "rounded_to_nearest_whole",
                                "rounded_up",
                            }
                            nasdaq_result["round_up_confirmed"] = llm_round_up
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

        text = normalize_cash_in_lieu_phrases(text).lower()
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
