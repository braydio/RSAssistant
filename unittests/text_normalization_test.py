import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.text_normalization import normalize_cash_in_lieu_phrases


def test_normalize_cash_in_lieu_variants():
    raw_text = "The notice mentions cache and loo as consideration."
    normalized = normalize_cash_in_lieu_phrases(raw_text)
    assert "cache and loo" not in normalized.lower()
    assert "cash in lieu" in normalized.lower()


def test_normalize_cash_in_lieu_handles_multiple_matches():
    raw_text = "cache and loo will be paid; CACHE AND LOO again later."
    normalized = normalize_cash_in_lieu_phrases(raw_text)
    assert normalized.lower().count("cash in lieu") == 2
