"""Blocking reverse-split policy analysis behind a Discord-free service API."""

from utils.logging_setup import logger
from utils.policy_resolver import SplitPolicyResolver


class PolicyAnalysisService:
    """Coordinate full policy analysis using the established resolver."""

    def __init__(self, resolver=None):
        self.resolver = resolver or SplitPolicyResolver()

    def full_analysis(self, nasdaq_url, ticker_hint=None, fallback_text=None):
        """Perform complete policy analysis for a NASDAQ notice URL.

        The resolver performs synchronous network and model work. Async bot
        callers must invoke this method through ``asyncio.to_thread``.
        """
        try:
            logger.info("Starting full_analysis for: %s", nasdaq_url)
            return self.resolver.full_analysis(
                nasdaq_url,
                ticker_hint=ticker_hint,
                fallback_text=fallback_text,
            )
        except Exception as exc:
            logger.error("Critical failure during full_analysis: %s", exc)
            return None


policy_analysis_service = PolicyAnalysisService()
