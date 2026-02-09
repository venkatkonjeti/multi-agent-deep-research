"""
Web Scraper — Extracts clean text content from web URLs.
Uses httpx for async HTTP and BeautifulSoup for HTML parsing.
"""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from ..config import WEB_SCRAPE_TIMEOUT, WEB_SCRAPE_MAX_CONTENT_LENGTH

logger = logging.getLogger(__name__)

# Tags to remove entirely
_REMOVE_TAGS = {
    "script", "style", "nav", "footer", "header", "aside",
    "form", "button", "iframe", "noscript", "svg",
}

# Headers to mimic a browser
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


async def scrape_url(url: str) -> dict:
    """
    Fetch and extract clean text from a URL.
    Returns {url, title, content, success, error}.
    """
    try:
        async with httpx.AsyncClient(
            timeout=WEB_SCRAPE_TIMEOUT,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            # Not HTML — return raw text if it's text-based
            if "text/" in content_type:
                text = response.text[:WEB_SCRAPE_MAX_CONTENT_LENGTH]
                return {
                    "url": url,
                    "title": url.split("/")[-1],
                    "content": text,
                    "success": True,
                }
            return {
                "url": url,
                "title": "",
                "content": "",
                "success": False,
                "error": f"Unsupported content type: {content_type}",
            }

        soup = BeautifulSoup(response.text, "lxml")

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Remove unwanted tags
        for tag in soup.find_all(_REMOVE_TAGS):
            tag.decompose()

        # Try to find main content
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", {"role": "main"})
            or soup.find("div", class_=re.compile(r"content|article|post|entry", re.I))
            or soup.body
        )

        if main_content is None:
            main_content = soup

        # Extract text
        text = main_content.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = "\n".join(lines)

        # Truncate
        text = text[:WEB_SCRAPE_MAX_CONTENT_LENGTH]

        return {
            "url": url,
            "title": title,
            "content": text,
            "success": True,
        }

    except httpx.TimeoutException:
        logger.warning(f"Timeout scraping {url}")
        return {"url": url, "title": "", "content": "", "success": False, "error": "Timeout"}
    except Exception as e:
        logger.warning(f"Failed to scrape {url}: {e}")
        return {"url": url, "title": "", "content": "", "success": False, "error": str(e)}


async def scrape_urls(urls: list[str]) -> list[dict]:
    """Scrape multiple URLs concurrently."""
    import asyncio
    tasks = [scrape_url(url) for url in urls]
    return await asyncio.gather(*tasks)
