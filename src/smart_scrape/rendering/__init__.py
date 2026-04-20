"""Renderer strategy pattern for deal extraction output."""

from smart_scrape.rendering.base import Renderer, create_renderer
from smart_scrape.rendering.csv_renderer import CSVRenderer
from smart_scrape.rendering.json_renderer import JSONRenderer
from smart_scrape.rendering.text import TextRenderer

__all__ = [
    "CSVRenderer",
    "JSONRenderer",
    "Renderer",
    "TextRenderer",
    "create_renderer",
]
