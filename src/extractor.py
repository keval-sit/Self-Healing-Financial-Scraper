import time
import random
import requests
from bs4 import BeautifulSoup
from src import mock_server

class Extractor:
    def __init__(self, storage, selector_store):
        self.storage = storage
        self.selector_store = selector_store
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Mozilla/5.0 (X11; Linux x86_64)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X)"
        ]

    def fetch_page(self, url=None, local_html=None) -> str:
        if local_html is not None:
            return local_html
            
        if url is None:
            return mock_server.get_page_content()
            
        retries = 3
        for attempt in range(retries):
            try:
                headers = {"User-Agent": random.choice(self.user_agents)}
                time.sleep(1) # rate limit
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                return response.text
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return ""

    def extract_field(self, html, field_name, selector) -> dict:
        soup = BeautifulSoup(html, 'html.parser')
        element = soup.select_one(selector)
        
        if element:
            raw_value = element.get_text(strip=True)
            return {
                "field_name": field_name,
                "raw_value": raw_value,
                "selector": selector,
                "success": True,
                "element_html": str(element)
            }
        else:
            return {
                "field_name": field_name,
                "raw_value": "",
                "selector": selector,
                "success": False,
                "element_html": ""
            }

    def extract_all(self, html, selectors_dict) -> dict:
        results = {}
        for field_name, selector in selectors_dict.items():
            results[field_name] = self.extract_field(html, field_name, selector)
        return results
