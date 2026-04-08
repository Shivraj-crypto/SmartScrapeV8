from __future__ import annotations

from bs4 import BeautifulSoup

# Remove elements that are usually noise for downstream content processing.
REMOVABLE_TAGS = ("script", "style", "noscript", "svg", "canvas", "iframe")
STRUCTURAL_NOISE_SELECTORS = ("nav", "footer", "header", "aside")


def clean_html(html_content: str) -> str:
    if not html_content or not html_content.strip():
        return ""

    soup = BeautifulSoup(html_content, "lxml")

    for tag_name in REMOVABLE_TAGS:
        for element in soup.find_all(tag_name):
            element.decompose()

    for selector in STRUCTURAL_NOISE_SELECTORS:
        for element in soup.select(selector):
            element.decompose()

    root = soup.body if soup.body is not None else soup
    return root.prettify().strip()
