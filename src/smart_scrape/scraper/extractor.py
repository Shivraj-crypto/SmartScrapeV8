from __future__ import annotations

import logging

import html2text
from bs4 import BeautifulSoup
from bs4 import Comment
from bs4.element import Tag

logger = logging.getLogger(__name__)

# Remove elements that are usually noise for downstream content processing.
REMOVABLE_TAGS = ("script", "style", "noscript", "svg", "canvas", "iframe")
STRUCTURAL_NOISE_SELECTORS = ("nav", "footer", "header", "aside")
NOISE_ATTRIBUTE_KEYWORDS = (
    "header",
    "footer",
    "nav",
    "navbar",
    "menu",
    "sidebar",
    "sbar",
    "toolbar",
    "popup",
    "popover",
    "modal",
    "dialog",
    "cookie",
    "banner",
    "subscribe",
    "newsletter",
    "social",
    "share",
    "breadcrumb",
    "pagination",
    "pager",
    "related",
    "recommend",
    "hot-sale",
    "hotword",
    "download-app",
    "app-download",
    "notification",
    "alert",
    "chat",
    "support",
    "help-center",
    "footer__",
    "header__",
)
NOISE_ROLES = {
    "navigation",
    "banner",
    "contentinfo",
    "complementary",
    "dialog",
    "alertdialog",
}


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


def _safe_attr(element: Tag, key: str, default: object = "") -> object:
    if not isinstance(getattr(element, "attrs", None), dict):
        return default
    return element.attrs.get(key, default)


def _matches_noise_attributes(element: Tag) -> bool:
    role = str(_safe_attr(element, "role", "")).strip().lower()
    if role in NOISE_ROLES:
        return True

    attribute_values: list[str] = []
    for key in ("id", "class", "aria-label", "data-testid"):
        value = _safe_attr(element, key, None)
        if isinstance(value, (list, tuple)):
            attribute_values.extend(str(item).lower() for item in value)
        elif value:
            attribute_values.append(str(value).lower())

    return any(
        keyword in attribute_value
        for attribute_value in attribute_values
        for keyword in NOISE_ATTRIBUTE_KEYWORDS
    )


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
        if _matches_noise_attributes(element):
            element.decompose()

    for element in soup.find_all(True):
        if not isinstance(element, Tag):
            continue
        if _is_empty_wrapper(element):
            element.decompose()

    root = soup.body if soup.body is not None else soup
    result = root.prettify().strip()
    logger.debug("clean_html: %d → %d chars", len(html_content), len(result))
    return result


def html_to_text(cleaned_html: str) -> str:
    if not cleaned_html or not cleaned_html.strip():
        return ""

    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_links = False
    converter.ignore_images = True
    converter.ignore_emphasis = True

    markdown_text = converter.handle(cleaned_html)
    normalized_lines = [line.rstrip() for line in markdown_text.splitlines()]
    return "\n".join(normalized_lines).strip()
