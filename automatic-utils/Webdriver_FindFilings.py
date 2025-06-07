import requests
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# Adjustable Configuration
START_DATE = (datetime.today() - timedelta(days=2)).strftime('%Y-%m-%d')
SEARCH_TERMS = {
    "keywords": ["reverse stock split", "no fractional shares", "reverse split"],
    "in_lieu_keywords": ["in lieu"],
    "preserve_round_lot_keywords": ["preserve round lot"]
}
BASE_URL = "https://efts.sec.gov/LATEST/search-index"
HEADERS = {"User-Agent": "MyApp/1.0 (my.email@example.com)"}
END_DATE = datetime.today().strftime('%Y-%m-%d')

def get_search_params():
    return {
        "q": " OR ".join([
            f"\"{term}\"" for term in SEARCH_TERMS["keywords"]
        ]) + " OR " + " OR ".join([
            f"\"{term}\"" for term in SEARCH_TERMS["in_lieu_keywords"]
        ]) + " OR " + " OR ".join([
            f"\"{term}\"" for term in SEARCH_TERMS["preserve_round_lot_keywords"]
        ]),
        "dateRange": "custom",
        "startdt": START_DATE,
        "enddt": END_DATE,
        "category": "full",
        "start": 0,
        "count": 100
    }

def extract_excerpt(filing_url):
    """Extract the matching excerpt from the filing."""
    try:
        response = requests.get(filing_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        text_content = soup.get_text()

        excerpts = []
        for keyword in SEARCH_TERMS["keywords"]:
            if keyword.lower() in text_content.lower():
                start = max(text_content.lower().find(keyword.lower()) - 50, 0)
                end = text_content.lower().find(keyword.lower()) + len(keyword) + 50
                snippet = text_content[start:end].strip()
                excerpts.append(snippet)

        return "\n".join(excerpts) if excerpts else "No matching excerpt found."
    except Exception as e:
        return f"Error extracting excerpt: {e}"

def process_filings(data, include_excerpt=False):
    results = []
    if 'hits' in data and 'hits' in data['hits']:
        for result in data['hits']['hits']:
            form_type = result['_source'].get('form', 'N/A')
            if form_type in ['8-K', 'S-1', 'S-3', 'S-4', '14A', '10-K', '10-Q']:
                company_info = result['_source'].get('display_names', ['N/A'])[0]
                filing_info = {
                    "company_name": company_info.split('(')[0].strip(),
                    "form_type": form_type,
                    "description": result['_source'].get('file_description', 'N/A'),
                    "file_date": result['_source'].get('file_date', 'N/A'),
                    "filing_url": result['_source'].get('accession_number', 'N/A')
                }
                if include_excerpt:
                    filing_info["excerpt"] = extract_excerpt(filing_info["filing_url"])
                results.append(filing_info)
    return results

def fetch_results(include_excerpt=False):
    """Fetch results and optionally include excerpts."""
    try:
        search_params = get_search_params()
        response = requests.get(BASE_URL, params=search_params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

        results = process_filings(data, include_excerpt=include_excerpt)
        return results
    except Exception as e:
        return f"Error fetching results: {e}"
