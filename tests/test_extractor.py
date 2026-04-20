"""Tests for HTML cleaning and text conversion."""

from __future__ import annotations

from smart_scrape.scraper.extractor import clean_html, html_to_text


class TestCleanHtml:
    def test_removes_script_tags(self):
        html = "<html><body><script>alert(1)</script><p>Hello</p></body></html>"
        result = clean_html(html)
        assert "alert" not in result
        assert "Hello" in result

    def test_removes_style_tags(self):
        html = "<html><body><style>.x{color:red}</style><p>Visible</p></body></html>"
        result = clean_html(html)
        assert "color:red" not in result
        assert "Visible" in result

    def test_removes_nav_footer_header(self, noisy_html: str):
        result = clean_html(noisy_html)
        assert "Main nav" not in result
        assert "Header content" not in result
        assert "Footer links" not in result
        assert "Sidebar promo" not in result

    def test_removes_hidden_elements(self, noisy_html: str):
        result = clean_html(noisy_html)
        assert "Hidden content" not in result
        assert "Also hidden" not in result

    def test_removes_cookie_banner(self, noisy_html: str):
        result = clean_html(noisy_html)
        assert "cookie" not in result.lower()

    def test_preserves_main_content(self, noisy_html: str):
        result = clean_html(noisy_html)
        assert "Visible Main Content" in result
        assert "This paragraph should remain" in result

    def test_returns_empty_for_blank_input(self):
        assert clean_html("") == ""
        assert clean_html("   ") == ""

    def test_removes_html_comments(self):
        html = "<html><body><!-- comment --><p>Text</p></body></html>"
        result = clean_html(html)
        assert "comment" not in result
        assert "Text" in result

    def test_removes_aria_hidden(self):
        html = '<html><body><div aria-hidden="true">Secret</div><p>Public</p></body></html>'
        result = clean_html(html)
        assert "Secret" not in result
        assert "Public" in result


class TestHtmlToText:
    def test_converts_html_to_markdown(self):
        html = "<h1>Title</h1><p>Paragraph text.</p>"
        result = html_to_text(html)
        assert "Title" in result
        assert "Paragraph text" in result

    def test_returns_empty_for_blank(self):
        assert html_to_text("") == ""

    def test_preserves_links(self):
        html = '<p>Visit <a href="https://example.com">Example</a></p>'
        result = html_to_text(html)
        assert "example.com" in result.lower()

    def test_strips_trailing_whitespace(self):
        html = "<p>Line one   </p><p>Line two   </p>"
        result = html_to_text(html)
        for line in result.splitlines():
            assert line == line.rstrip()
