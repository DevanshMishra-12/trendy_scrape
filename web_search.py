# web_search.py
import os
import requests
import urllib.parse
from typing import List, Optional
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
# NOTE: adjust base if your Firecrawl account uses a different host
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.com/v2/search"

def debug_print_firecrawl_response(resp: requests.Response):
    try:
        print("Firecrawl status:", resp.status_code)
        # print a truncated body to avoid huge logs
        text = resp.text or ""
        print("Firecrawl response (first 1000 chars):", text[:1000].replace("\n", " "))
    except Exception as e:
        print("Could not print Firecrawl response:", e)

def firecrawl_search(query: str, site: str = "", num_results: int = 5) -> List[str]:
    """
    Use Firecrawl Search API to fetch top results.
    Returns a list of URLs (strings).
    If Firecrawl fails, returns an empty list (caller should fallback).
    """
    if not FIRECRAWL_API_KEY:
        print("⚠️ FIRECRAWL_API_KEY not set in environment.")
        return []

    q = f"site:{site} {query}" if site else query
    headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}
    payload = {"query": q, "limit": num_results}

    try:
        resp = requests.post(FIRECRAWL_SEARCH_URL, json=payload, headers=headers, timeout=30)
    except Exception as e:
        print("⚠️ Network error calling Firecrawl:", e)
        return []

    # If non-200, print debug info and return empty so caller falls back
    if resp.status_code != 200:
        debug_print_firecrawl_response(resp)
        if resp.status_code == 401 or resp.status_code == 403:
            print("🔒 Authentication / permission error from Firecrawl. Check your FIRECRAWL_API_KEY and account permissions.")
        elif resp.status_code == 429:
            print("⏳ Rate limited by Firecrawl (429). Try again later or reduce request rate.")
        else:
            print("⚠️ Firecrawl returned non-200 status.")
        return []

    # try to parse JSON
    try:
        data = resp.json()
    except Exception as e:
        print("⚠️ Failed to parse Firecrawl JSON:", e)
        debug_print_firecrawl_response(resp)
        return []

    # Look for results array in common shapes
    results = []
    # many Firecrawl responses include "results" as a list of dicts with "url"
    for key in ("results", "data", "items"):
        if isinstance(data.get(key), list):
            for it in data.get(key, []):
                if isinstance(it, dict):
                    url = it.get("url") or it.get("link") or it.get("target")
                    if url:
                        results.append(url)
            if results:
                return results[:num_results]

    # Fallback: top-level 'results' not found; attempt to find URLs anywhere in the JSON
    def extract_urls_from_obj(obj):
        found = []
        if isinstance(obj, dict):
            for v in obj.values():
                found += extract_urls_from_obj(v)
        elif isinstance(obj, list):
            for v in obj:
                found += extract_urls_from_obj(v)
        elif isinstance(obj, str):
            if obj.startswith("http"):
                found.append(obj)
        return found

    extracted = extract_urls_from_obj(data)
    # dedupe keeping order
    uniq = []
    seen = set()
    for u in extracted:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq[:num_results]

# -------------------------
# DuckDuckGo fallback search (HTML)
# -------------------------
def ddg_search(query: str, num_results: int = 5) -> List[str]:
    """
    Simple DuckDuckGo HTML search fallback.
    Uses the lightweight HTML endpoint to avoid heavy JS.
    """
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        resp = requests.post(url, data=params, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print("⚠️ DuckDuckGo search failed:", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    # DuckDuckGo HTML returns results in <a class="result__a" href="...">
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # ignore internal links
        if href.startswith("/"):
            continue
        if href.startswith("http"):
            links.append(href)
        if len(links) >= num_results:
            break

    # dedupe
    uniq = []
    seen = set()
    for u in links:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq[:num_results]

# -------------
# Public API-compatible wrappers
# -------------
def search_all(query: str, site: str = "", num_results: int = 5) -> List[str]:
    # Try Firecrawl first
    fc = firecrawl_search(query, site, num_results)
    if fc:
        return fc
    # If Firecrawl failed, fallback to DuckDuckGo
    print("⚠️ Falling back to DuckDuckGo HTML search (Firecrawl failed).")
    ddg = ddg_search(f"{'site:' + site + ' ' if site else ''}{query}", num_results=num_results)
    return ddg

def main(query: str, site: str = "", num_results: int = 1) -> Optional[str]:
    results = search_all(query, site, num_results)
    return results[0] if results else None

# quick CLI test
if __name__ == "__main__":
    q = input("Enter search query: ")
    print("Candidates:", search_all(q, num_results=5))
