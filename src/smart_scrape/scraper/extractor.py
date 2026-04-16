from __future__ import annotations

from bs4 import BeautifulSoup
from bs4 import Comment
from bs4.element import Tag

# Remove elements that are usually noise for downstream content processing.
REMOVABLE_TAGS = ("script", "style", "noscript", "svg", "canvas", "iframe")
STRUCTURAL_NOISE_SELECTORS = ("nav", "footer", "header", "aside")


def _is_hidden(element: Tag) -> bool:
    if not isinstance(element.attrs, dict):
        return False

    if element.has_attr("hidden"):
        return True
    if str(element.get("aria-hidden", "")).lower() == "true":
        return True

    style = str(element.get("style", "")).replace(" ", "").lower()
    return any(
        token in style
        for token in ("display:none", "visibility:hidden", "opacity:0")
    )


def _is_empty_wrapper(element: Tag) -> bool:
    if element.name not in {"div", "span", "section"}:
        return False
    if element.find(["img", "video", "iframe", "a", "button", "input", "textarea"]):
        return False
    return not element.get_text(strip=True)


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

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for element in soup.find_all(True):
        if not isinstance(element, Tag):
            continue
        if _is_hidden(element):
            element.decompose()

    for element in soup.find_all(True):
        if not isinstance(element, Tag):
            continue
        if _is_empty_wrapper(element):
            element.decompose()

    root = soup.body if soup.body is not None else soup
    return root.prettify().strip()
