# main.py
import streamlit as st
from web_search import main as search_top, search_all
from web_scraper import scrape_website, extract_body_content, clean_body_content

st.set_page_config(page_title="Trendy Bot", layout="wide")
st.title("Trendy Bot")

site_choice = st.selectbox(
    "Restrict search to a site (optional):",
    ("", "amazon.in", "flipkart.com", "wikipedia.org", "nytimes.com")
)

query = st.text_input("What are you looking for buddy?")

if st.button("Search & Scrape"):
    if not query or not query.strip():
        st.error("Please enter a query before searching.")
    else:
        # Get up to 5 candidate URLs
        try:
            candidates = search_all(query, site=site_choice, num_results=5)
        except Exception as e:
            st.error(f"Search failed: {e}")
            candidates = []

        if not candidates:
            st.warning("No search results found. Try a simpler query or remove site restriction.")
        else:
            st.write("Top candidate URLs (pick one to scrape):")
            for i, u in enumerate(candidates, start=1):
                st.write(f"{i}. {u}")

            idx = st.number_input("Index to scrape", min_value=1, max_value=len(candidates), value=1)
            url_to_scrape = candidates[idx - 1]
            st.write("Selected URL:", url_to_scrape)

            try:
                with st.spinner(f"Scraping {url_to_scrape} ..."):
                    dom_content = scrape_website(url_to_scrape)
                    body_content = extract_body_content(dom_content)
                    cleaned_content = clean_body_content(body_content)

                st.session_state.dom_content = cleaned_content
                with st.expander("View DOM Content"):
                    st.text_area("DOM Content", cleaned_content or "<empty>", height=400)
            except ValueError as ve:
                st.error(f"Invalid URL: {ve}")
            except Exception as e:
                st.error(f"Scraping failed: {e}")
