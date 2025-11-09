# web_scraper.py
import os
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# Optional: validators to check URL shape (pip install validators)
try:
    import validators
except Exception:
    validators = None

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
FIRECRAWL_API_BASE = "https://api.firecrawl.com/v2/scrape"

CHROMEDRIVER_PATH = "chromedriver.exe"  # adjust path if necessary

def normalize_url(url: str) -> str | None:
    if not url:
        return None
    u = str(url).strip()
    if not u:
        return None
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u

def scrape_with_firecrawl(url: str) -> str | None:
    """Try Firecrawl API first (if key is present). Returns HTML string or None."""
    if not FIRECRAWL_API_KEY:
        return None
    try:
        headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}
        payload = {"url": url, "formats": ["html"], "options": {"stealth": True, "timeout": 20}}
        resp = requests.post(FIRECRAWL_API_BASE, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        html = (
            data.get("html")
            or data.get("content")
            or (data.get("results", [{}])[0].get("html") if data.get("results") else None)
        )
        return html
    except Exception:
        return None

def scrape_with_selenium(url: str, headless: bool = True, wait_seconds: float = 3.0) -> str:
    """Selenium fallback. Returns page_source (HTML)."""
    options = Options()
    if headless:
        # new headless flag for modern Chrome versions
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(url)
        time.sleep(wait_seconds)  # allow JS to render
        return driver.page_source
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def scrape_website(url: str) -> str:
    """
    Top-level scraper: validate & normalize URL, then try Firecrawl, else Selenium.
    Raises ValueError if url is invalid/unusable.
    Returns HTML string.
    """
    if not url:
        raise ValueError("scrape_website expected a non-empty URL but got None/empty.")

    url_norm = normalize_url(url)
    if not url_norm:
        raise ValueError(f"Cannot normalize URL: {url!r}")

    # Optionally validate URL format
    if validators:
        if not validators.url(url_norm):
            raise ValueError(f"Normalized URL does not appear valid: {url_norm}")

    # Try Firecrawl first
    html = scrape_with_firecrawl(url_norm)
    if html:
        print("✅ Got HTML from Firecrawl")
        return html
    else:
        print("⚠️ Firecrawl did not return HTML or not available. Falling back to Selenium.")

    # Selenium fallback
    html = scrape_with_selenium(url_norm)
    return html

# small helpers for post-processing
def extract_body_content(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body
    return str(body) if body else ""

def clean_body_content(body_content: str) -> str:
    soup = BeautifulSoup(body_content, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return text

def split_dom_content(dom_content: str, max_length: int = 6000):
    return [dom_content[i : i + max_length] for i in range(0, len(dom_content), max_length)]
