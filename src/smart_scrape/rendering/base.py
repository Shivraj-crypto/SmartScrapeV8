"""Abstract renderer base and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod

from smart_scrape.processor.models import ExtractionReport


class Renderer(ABC):
    """Strategy interface for rendering extraction reports."""

    format_name: str = ""

    @abstractmethod
    def render(self, report: ExtractionReport) -> str:
        """Serialise *report* to a string in the target format."""
        ...

    @property
    def file_extension(self) -> str:
        """Suggested file extension (without leading dot)."""
        return "txt"


def create_renderer(format_name: str) -> Renderer:
    """Factory: return the renderer for the requested format.

    Raises ``ValueError`` for unknown formats.
    """
    # Avoid circular imports — import here.
    from smart_scrape.rendering.csv_renderer import CSVRenderer
    from smart_scrape.rendering.json_renderer import JSONRenderer
    from smart_scrape.rendering.text import TextRenderer

    renderers: dict[str, type[Renderer]] = {
        "text": TextRenderer,
        "json": JSONRenderer,
        "csv": CSVRenderer,
    }
    cls = renderers.get(format_name.lower())
    if cls is None:
        available = ", ".join(sorted(renderers))
        raise ValueError(
            f"Unknown output format '{format_name}'. "
            f"Available: {available}"
        )
    return cls()
