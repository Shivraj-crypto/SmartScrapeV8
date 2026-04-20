"""Shared test fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src/ is on the path for test runs.
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


@pytest.fixture
def sample_retailmenot_html() -> str:
    """Minimal RetailMeNot-like HTML with offer strips."""
    return """
    <html><body>
    <h1>TestStore Coupons &amp; Promo Codes</h1>
    <a data-component-class="offer_strip"
       x-data="{'offerType': 'coupon'}">
        <span>Code</span>
        <h3>20% Off Your Purchase</h3>
        <div>Limited time</div>
        <div>Show Code</div>
    </a>
    <a data-component-class="offer_strip"
       x-data="{'offerType': 'sale'}">
        <span>Sale</span>
        <h3>Free Shipping On Orders $50+</h3>
        <div>Get Deal</div>
    </a>
    <a data-component-class="offer_strip">
        <span>Online Cash Back</span>
        <h3>5% Cash Back For Purchases Sitewide</h3>
        <div>Limited time</div>
    </a>
    <a data-component-class="offer_strip">
        <h3>Buy 1, Get 1 Free on Accessories</h3>
        <div>Get Deal</div>
    </a>
    <a data-component-class="offer_strip">
        <span>Code</span>
        <h3>$10 Off Orders Over $75</h3>
        <div>Expiring soon</div>
        <div>Show Code</div>
    </a>
    </body></html>
    """


@pytest.fixture
def sample_generic_text() -> str:
    """Plain text with deal signals for the generic extractor."""
    return """
    Visit TestStore for great deals!
    Save 25% off your first order with code WELCOME25.
    Get $15 off orders over $100.
    Free shipping on all orders.
    Members get 3% cash back sitewide.
    Buy 2, Get 1 free on select items.
    Check out our latest arrivals.
    Contact support at help@store.com.
    """


@pytest.fixture
def noisy_html() -> str:
    """HTML with nav, footer, hidden elements, and cookie banners."""
    return """
    <html><body>
    <nav>Main nav links here</nav>
    <header>Header content</header>
    <div class="cookie-banner">Accept cookies</div>
    <div style="display:none">Hidden content</div>
    <div hidden>Also hidden</div>
    <main>
        <h1>Visible Main Content</h1>
        <p>This paragraph should remain.</p>
        <div class="deal">Real deal: 50% off everything</div>
    </main>
    <footer>Footer links</footer>
    <aside>Sidebar promo</aside>
    </body></html>
    """
