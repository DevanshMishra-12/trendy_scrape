# trendy_scrape

🧠 Trendy Bot — Smart Search & Web Scraper (Streamlit App)
Trendy Bot is a lightweight search + scrape assistant built with Streamlit, capable of:
Searching the web using Firecrawl Search API (optional)
Falling back to DuckDuckGo HTML search if Firecrawl isn’t available
Scraping webpages using either:
Firecrawl Scrape API (if API key exists), or
Requests + BeautifulSoup (Streamlit Cloud–friendly)
Cleaning and displaying webpage text content inside a sleek Streamlit interface
The app is designed for deployment on Streamlit Cloud, with no Selenium required.

🚀 Features
🔍 1. Search Engine Integration
Uses Firecrawl Search when FIRECRAWL_API_KEY is provided.
Automatic fallback to DuckDuckGo HTML search when Firecrawl is unavailable.
Supports site-restricted search, e.g.:
amazon.in
flipkart.com
wikipedia.org
nytimes.com

🕸️ 2. Web Scraping
Tries Firecrawl Scrape API first (handles JS-rendered pages).
Falls back to a clean requests + BeautifulSoup scraper.
Fully Streamlit Cloud compatible (no browser automation required).

🧼 3. Content Cleaning & Display
Extracts <body> content.
Removes scripts, styles, and unnecessary markup.
Displays readable, clean text inside the app.

🖥️ 4. Streamlit UI
Minimal and intuitive interface:
Enter query
Choose optional site restriction
See top URLs
Select one to scrape
View cleaned content inside an expandable text area

📂 Project Structure
trendy_scrape/
│
├── main.py                # Streamlit UI
├── web_search.py          # Firecrawl + DuckDuckGo search
├── web_scraper.py         # Firecrawl + requests-based scraper
├── requirements.txt       # Required dependencies
└── README.md              # Project documentation

🔧 Installation & Setup
1️⃣ Clone the repository
git clone https://github.com/yourusername/trendy_scrape.git
cd trendy_scrape
2️⃣ Install dependencies
pip install -r requirements.txt
3️⃣ (Optional) Add Firecrawl API Key
Create a .env file in the project root:
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
If no key is provided, Firecrawl is skipped and DuckDuckGo is used.
▶️ Run the App Locally
streamlit run main.py

The app will open in your browser.

☁️ Deploy to Streamlit Cloud
Push your code to GitHub
Go to share.streamlit.io
Select your repository
Set Main file = main.py
Add your Firecrawl API key inside:
Settings → Secrets / Environment Variables


That’s it—Streamlit Cloud will deploy automatically.

✔ No Selenium required
✔ No Chrome/ChromeDriver setup
✔ Fast and stable deployment

🛠️ Tech Stack
Python
Streamlit (frontend UI)
Requests (HTTP fetching)
BeautifulSoup4 (HTML parsing)
Firecrawl API (optional enhanced search + JS-rendered scraping)
DuckDuckGo HTML search (fallback search)

🧩 How it Works (Architecture)
          ┌────────────────────────┐
          │  User enters a query   │
          └─────────────┬──────────┘
                        ▼
            ┌─────────────────────┐
            │   Search Engine     │
            │ Firecrawl → DDG     │
            └─────────┬───────────┘
                      ▼
         ┌───────────────────────────┐
         │  User selects a URL       │
         └──────────────┬────────────┘
                        ▼
       ┌─────────────────────────────────┐
       │   Scraper Module                │
       │ Firecrawl → requests + BS4      │
       └─────────────────┬───────────────┘
                         ▼
            ┌─────────────────────────┐
            │ Clean + extract content │
            └───────────────┬────────┘
                            ▼
               ┌────────────────────┐
               │  Display in UI     │
               └────────────────────┘

🧪 Testing Search from the Command Line
python web_search.py
Enter search query: iphone 16 amazon

📝 Future Enhancements
Add summarization (LLM integration)
Add keyword extraction
Add image scraping
Add multiple results comparison panel

🤝 Contributing
Pull requests and suggestions are welcome!
If you want help extending the app, feel free to open an issue.
