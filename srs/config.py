import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
MOCK_SITE_DIR = BASE_DIR / "mock_site"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "scraper.db"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-6"

MOCK_SITE_ID = "mock_financial_site"
MOCK_SERVER_PORT = 8765
MOCK_SERVER_URL = f"http://localhost:{MOCK_SERVER_PORT}"

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

FIELDS = {
    "company_name": {
        "display_name": "Company Name", 
        "field_type": "text", 
        "pattern": r'^[A-Za-z][A-Za-z0-9\s\.\,\&\-\(\)]+$', 
        "synonyms": ["Company", "Name", "Company Name", "Equity Name", "Scrip Name"], 
        "min_val": None, 
        "max_val": None, 
        "drift_threshold": None
    },
    "stock_price": {
        "display_name": "Stock Price", 
        "field_type": "currency", 
        "pattern": r'[\$₹]?\s*[\d,]+\.?\d*', 
        "synonyms": ["Price", "Stock Price", "Current Price", "LTP", "Last Traded Price", "CMP", "Close Price"], 
        "min_val": 0.01, 
        "max_val": 1000000, 
        "drift_threshold": 0.5
    },
    "day_change_pct": {
        "display_name": "Day Change %", 
        "field_type": "percentage", 
        "pattern": r'[+-]?\s*\d+\.?\d*\s*%', 
        "synonyms": ["Change %", "Day Change", "% Change", "Pct Change", "Change", "Chg%"], 
        "min_val": -100, 
        "max_val": 1000, 
        "drift_threshold": None
    },
    "market_cap": {
        "display_name": "Market Cap", 
        "field_type": "abbreviated", 
        "pattern": r'[\$₹]?\s*[\d,]+\.?\d*\s*[BMTKbmtk]', 
        "synonyms": ["Market Cap", "Mkt Cap", "Market Capitalization", "M.Cap", "MCap"], 
        "min_val": None, 
        "max_val": None, 
        "drift_threshold": 0.5
    },
    "pe_ratio": {
        "display_name": "P/E Ratio", 
        "field_type": "numeric", 
        "pattern": r'\d+\.?\d*', 
        "synonyms": ["P/E", "P/E Ratio", "PE Ratio", "P/E (TTM)", "Price to Earnings", "PE (TTM)"], 
        "min_val": 0, 
        "max_val": 500, 
        "drift_threshold": 0.3
    },
    "volume": {
        "display_name": "Volume", 
        "field_type": "abbreviated", 
        "pattern": r'[\d,]+\.?\d*\s*[BMKbmk]?', 
        "synonyms": ["Volume", "Vol", "Trading Volume", "Day Volume", "Traded Vol"], 
        "min_val": None, 
        "max_val": None, 
        "drift_threshold": None
    }
}

MOCK_V1_SELECTORS = {
    "company_name": "h1.company-name",
    "stock_price": "span.stock-price",
    "day_change_pct": "span.change-percent",
    "market_cap": "#metric-market-cap .metric-value",
    "pe_ratio": "#metric-pe-ratio .metric-value",
    "volume": "#metric-volume .metric-value",
}
