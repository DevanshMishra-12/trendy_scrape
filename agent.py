# agent.py
import os
import sys
import asyncio
import json
import traceback
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from bs4 import BeautifulSoup
from urllib.parse import urljoin

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import BaseTool

# Import your search + scraper modules
from web_search import search_all
from web_scraper import scrape_website, extract_body_content, clean_body_content

# -----------------------------
# Load Environment Variables
# -----------------------------
load_dotenv(dotenv_path=r"D:/projects/trendy_bot/.env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY not found in .env or environment.")
    sys.exit(1)

if not FIRECRAWL_API_KEY:
    print("ERROR: FIRECRAWL_API_KEY not found in .env or environment.")
    sys.exit(1)

# Some libs may also read GEMINI_API_KEY from env
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

print("GEMINI key present:", bool(GEMINI_API_KEY))
print("FIRECRAWL key present:", bool(FIRECRAWL_API_KEY))

# -----------------------------
# Robust model selection: try multiple model candidates and pick the first that constructs
# -----------------------------
candidates_env = os.getenv(
    "MODEL_NAME_CANDIDATES",
    "gemini-1.5-flash,gemini-1.5,gemini-1.0,gemini-pro,gemini-1.5-preview"
)
MODEL_CANDIDATES = [c.strip() for c in candidates_env.split(",") if c.strip()]

if not MODEL_CANDIDATES:
    raise RuntimeError("No model candidates configured in MODEL_NAME_CANDIDATES")

def make_google_model(api_key: str):
    """Try to instantiate ChatGoogleGenerativeAI with candidate model IDs.
    Do not perform test generation calls here because different client versions
    accept different message shapes. Only try to construct; if construction
    raises, try next candidate. If all fail, raise with helpful guidance.
    """
    last_exc = None
    for candidate in MODEL_CANDIDATES:
        try:
            print(f"Trying Google model candidate: {candidate}")
            model_candidate = ChatGoogleGenerativeAI(
                model=candidate,
                google_api_key=api_key,
                temperature=0.7,
            )
            # If instantiation didn't raise, accept the candidate.
            print(f"✅ Using model: {candidate}")
            return model_candidate
        except Exception as e:
            last_exc = e
            print(f"Model '{candidate}' failed to initialize: {e}")
            tb = traceback.format_exc(limit=1)
            print(tb)
            # continue to next candidate

    msg = (
        "All configured model candidates failed to instantiate. Last error:\n"
        f"{last_exc}\n\n"
        "How to resolve:\n"
        "  1) Open Google Cloud Console -> Generative AI / Models and confirm a model ID supported by your project/region.\n"
        "  2) Or run (if you have gcloud):\n"
        "       gcloud ai models list --region=<your-region>\n"
        "  3) Update env var MODEL_NAME_CANDIDATES with a valid model id (comma-separated).\n"
        "  4) Ensure your GEMINI_API_KEY has correct permissions and you've enabled the Generative AI APIs in the project.\n"
    )
    raise RuntimeError(msg)

# Create the model (will try candidates)
model = make_google_model(GEMINI_API_KEY)

# -----------------------------
# Async HTTP fallback for Firecrawl v2 (/v2/query)
# -----------------------------
class FirecrawlHTTPFallback:
    BASE_URL = "https://api.firecrawl.dev"  # change if your endpoint differs

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def query(self, query_text: str, model: str = "firecrawl-latest", max_output_tokens: int = 600) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/v2/query"
        prompt = (
            f"Extract the top 6 relevant products for the user query: \"{query_text}\".\n"
            "Prefer results from Amazon India and Flipkart if available. "
            "Return a JSON array (not text) where each element has: name, price, link, image_url. "
            "If price is unavailable return null. Respond with pure JSON."
        )

        payload = {
            "query": query_text,
            "prompt": prompt,
            "model": model,
            "max_output_tokens": max_output_tokens
        }

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(f"Firecrawl HTTP error: {resp.status_code} {resp.text}")

        try:
            return resp.json()
        except Exception:
            return {"raw_text": resp.text}

# -----------------------------
# Helper: detect product queries
# -----------------------------
def is_product_query(user_input: str) -> bool:
    keywords = [
        "laptop", "dress", "shoes", "mobile", "phone", "gpu", "watch",
        "bag", "tv", "trendy", "fashion", "clothes", "tshirt", "t-shirt", "t shirts", "tshirts",
        "jeans", "under", "budget", "best", "top", "buy"
    ]
    return any(word in user_input.lower() for word in keywords)

# -----------------------------
# Firecrawl MCP server parameters (npx firecrawl-mcp)
# -----------------------------
server_params = StdioServerParameters(
    command="npx",
    env={"FIRECRAWL_API_KEY": FIRECRAWL_API_KEY},
    args=["firecrawl-mcp"]
)

# -----------------------------
# Utility: safely extract text from agent response
# -----------------------------
def extract_agent_text(resp: Any) -> str:
    try:
        if resp is None:
            return "<no response>"

        if isinstance(resp, str):
            return resp

        if isinstance(resp, dict):
            if "messages" in resp and isinstance(resp["messages"], list) and resp["messages"]:
                last = resp["messages"][-1]
                if isinstance(last, dict):
                    return last.get("content") or last.get("text") or json.dumps(last)
            if "content" in resp:
                return resp["content"]
            return json.dumps(resp, indent=2)
        if hasattr(resp, "messages"):
            msgs = getattr(resp, "messages")
            if isinstance(msgs, list) and msgs:
                last = msgs[-1]
                if isinstance(last, dict):
                    return last.get("content") or str(last)
                if hasattr(last, "content"):
                    return getattr(last, "content")
            return str(resp)

        return str(resp)
    except Exception:
        try:
            return str(resp)
        except Exception:
            return "<unable to extract text>"

# -----------------------------
# Format product results for printing
# -----------------------------
def pretty_print_products(products: Any):
    try:
        if products is None:
            print("No product results.")
            return

        if isinstance(products, dict):
            for possible in ("items", "results", "products", "hits", "data"):
                if possible in products and isinstance(products[possible], list):
                    products = products[possible]
                    break
            if isinstance(products, dict) and "raw_text" in products:
                try:
                    parsed = json.loads(products["raw_text"])
                    products = parsed if isinstance(parsed, list) else [parsed]
                except Exception:
                    print(products["raw_text"])
                    return

        if isinstance(products, list):
            if not products:
                print("No products found.")
                return
            for idx, item in enumerate(products[:10], start=1):
                if isinstance(item, str):
                    try:
                        item = json.loads(item)
                    except Exception:
                        print(f"{idx}. {item}")
                        continue
                name = item.get("name") or item.get("title") or "<no-name>"
                price = item.get("price") or item.get("price_str") or item.get("amount") or "<no-price>"
                link = item.get("link") or item.get("url") or item.get("product_url") or "<no-link>"
                image = item.get("image_url") or item.get("image") or item.get("images") or "<no-image>"
                print(f"{idx}. {name}")
                print(f"   Price: {price}")
                print(f"   Link:  {link}")
                if image:
                    print(f"   Image: {image}")
                print()
            return

        if isinstance(products, str):
            print(products)
            return

        print(json.dumps(products, indent=2))
    except Exception as e:
        print("Error formatting products:", e)
        print(repr(products))

# -----------------------------
# Parse product info from HTML (JSON-LD, meta tags, heuristics)
# -----------------------------
def parse_product_page(html: str, url: str) -> Dict[str, Optional[str]]:
    try:
        soup = BeautifulSoup(html, "html.parser")

        canonical = None
        can_tag = soup.find("link", rel="canonical")
        if can_tag and can_tag.get("href"):
            canonical = urljoin(url, can_tag["href"])
        else:
            canonical = url

        def meta_prop(prop_names):
            for p in prop_names:
                tag = soup.find("meta", property=p) or soup.find("meta", attrs={"name": p})
                if tag:
                    content = tag.get("content")
                    if content:
                        return content.strip()
            return None

        og_title = meta_prop(["og:title", "twitter:title", "title"])
        og_image = meta_prop(["og:image", "twitter:image", "image"])
        og_price = meta_prop(["product:price:amount", "og:price:amount", "price", "twitter:data1"])

        title_tag = soup.title.string.strip() if soup.title and soup.title.string else None

        name = None
        price = None
        image = None
        try:
            for script in soup.find_all("script", type="application/ld+json"):
                text = script.string
                if not text:
                    continue
                try:
                    data = json.loads(text.strip())
                except Exception:
                    continue

                items = data if isinstance(data, list) else [data]
                for it in items:
                    it_type = it.get("@type") or it.get("type")
                    if isinstance(it_type, list):
                        it_type = it_type[0]
                    if it_type and str(it_type).lower() == "product":
                        if not name:
                            name = it.get("name")
                        offers = it.get("offers")
                        if offers:
                            if isinstance(offers, list):
                                offers = offers[0]
                            price_val = offers.get("price") or (offers.get("priceSpecification") or {}).get("price")
                            if price_val:
                                price = str(price_val)
                            currency = offers.get("priceCurrency") or offers.get("currency")
                            if currency and price:
                                price = f"{price} {currency}"
                        img = it.get("image")
                        if img:
                            if isinstance(img, list):
                                image = img[0]
                            else:
                                image = img
                        if name:
                            break
        except Exception:
            pass

        if not name:
            name = og_title or title_tag
        if not image:
            image = og_image
        if not price:
            price = og_price

        if isinstance(image, list):
            image = image[0] if image else None

        return {
            "name": name,
            "price": price,
            "link": canonical,
            "image": image,
            "source_url": url,
            "raw_title": title_tag
        }
    except Exception as e:
        return {"name": None, "price": None, "link": url, "image": None, "source_url": url, "raw_title": None}

# -----------------------------
# Fetch products by searching+scraping
# -----------------------------
async def fetch_products_via_scrape(query: str, num_results: int = 6) -> List[Dict[str, Optional[str]]]:
    try:
        candidates = await asyncio.to_thread(search_all, query, "", num_results)
    except Exception as e:
        print("Error running search_all:", e)
        candidates = []

    products: List[Dict[str, Optional[str]]] = []
    for url in candidates:
        try:
            scraped = await asyncio.to_thread(scrape_website, url)
            if isinstance(scraped, dict):
                html = scraped.get("html") or ""
            else:
                html = scraped or ""
            if not html:
                continue
            parsed = parse_product_page(html, url)
            if not parsed.get("link"):
                parsed["link"] = url
            products.append(parsed)
        except Exception as e:
            print(f"Error scraping/parsing {url}: {e}")
            continue

    return products

# -----------------------------
# Main Async Agent Loop
# -----------------------------
async def main():
    fallback = FirecrawlHTTPFallback(FIRECRAWL_API_KEY)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            tools = await load_mcp_tools(session)

            try:
                available_tool_names = [getattr(t, "name", str(t)) for t in tools]
            except Exception:
                available_tool_names = [str(t) for t in tools]
            print("Available tools:", available_tool_names)
            print("-" * 60)

            agent = create_react_agent(model, tools)

            messages = [
                {"role": "system", "content": (
                    "You are a helpful assistant that can fetch trending products with links, "
                    "scrape websites using Firecrawl, and provide trend summaries."
                )}
            ]

            firecrawl_tool = None
            for t in tools:
                try:
                    name = getattr(t, "name", "") or getattr(t, "_name", "") or str(t)
                    if isinstance(name, str) and ("search_products" in name or ("search" in name and "product" in name)):
                        firecrawl_tool = t
                        break
                except Exception:
                    continue

            while True:
                user_input = await asyncio.to_thread(input, "\nYou: ")
                if user_input is None:
                    continue
                if user_input.strip().lower() == "quit":
                    print("Byee")
                    break

                if len(messages) > 40:
                    messages = [messages[0]] + messages[-20:]

                if is_product_query(user_input):
                    print("\n(Detected product query — fetching products...)")
                    products = None

                    # 1) Try MCP tool (preferred)
                    if firecrawl_tool is not None:
                        try:
                            if hasattr(firecrawl_tool, "arun"):
                                products = await firecrawl_tool.arun(user_input)
                            elif hasattr(firecrawl_tool, "_arun"):
                                products = await firecrawl_tool._arun(user_input)
                            elif hasattr(firecrawl_tool, "run"):
                                products = await asyncio.to_thread(firecrawl_tool.run, user_input)
                            else:
                                products = await asyncio.to_thread(lambda q: firecrawl_tool(q), user_input)
                        except Exception as e:
                            print("MCP tool call failed:", repr(e))
                            products = None

                    # 2) If MCP tool not available or failed, try HTTP fallback (v2 /v2/query)
                    if not products:
                        try:
                            products = await fallback.query(user_input, max_output_tokens=600)
                        except Exception as e:
                            print("HTTP fallback failed:", e)
                            products = None

                    # 3) If still nothing or to enrich, use search+scrape DOM extraction
                    try:
                        need_scrape = False
                        if not products:
                            need_scrape = True
                        else:
                            if isinstance(products, dict):
                                found_list = False
                                for key in ("items", "results", "products", "hits", "data"):
                                    if key in products and isinstance(products[key], list) and products[key]:
                                        found_list = True
                                        break
                                if not found_list:
                                    need_scrape = True
                            elif isinstance(products, list) and not products:
                                need_scrape = True
                            elif isinstance(products, str):
                                if len(products) < 10:
                                    need_scrape = True

                        if need_scrape:
                            scraped_products = await fetch_products_via_scrape(user_input, num_results=6)
                            if scraped_products:
                                products = scraped_products
                    except Exception as e:
                        print("Scrape fallback failed:", e)

                    # add the user's query to conversation so the agent can summarize
                    messages.append({"role": "user", "content": f"Summarize trending products and recommendations for: {user_input}"})

                    try:
                        resp = await agent.ainvoke({"messages": messages})
                        ai_summary = extract_agent_text(resp)
                    except Exception as e:
                        ai_summary = f"Error generating AI summary: {e}"

                    print("\n--- Trend Summary & Top Products ---")
                    print(ai_summary)
                    print("\n🔗 Products with links:")
                    pretty_print_products(products)
                    continue

                # Non-product queries: forward to agent
                messages.append({"role": "user", "content": user_input[:175000]})
                try:
                    response = await agent.ainvoke({"messages": messages})
                    if isinstance(response, dict) and "messages" in response and isinstance(response["messages"], list):
                        last_msg = response["messages"][-1]
                        if isinstance(last_msg, dict):
                            ai_text = last_msg.get("content") or last_msg.get("text") or str(last_msg)
                        else:
                            ai_text = getattr(last_msg, "content", str(last_msg))
                    else:
                        ai_text = extract_agent_text(response)
                    print("\nAgent:", ai_text)
                except Exception as e:
                    print(f"Error invoking agent: {e}")


# -----------------------------
# Run Async Main
# -----------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user — exiting.")
