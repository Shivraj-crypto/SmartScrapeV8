from __future__ import annotations

import importlib
from pathlib import Path


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

DEALS_SYSTEM_PROMPT = """You are a strict deals and coupons extraction assistant.
Only return deals, discounts, promo codes, cashback, or coupon offers from the uploaded file.
Ignore all unrelated content.

Output requirements:
- Plain text only.
- One deal per line.
- Use this exact format per line:
  STORE | OFFER | COUPON_CODE_OR_NO_CODE | CONDITIONS
- If no deals or coupons are present, return exactly:
  NO_DEALS_FOUND
"""

DEALS_USER_PROMPT = "Extract only deals and coupons from the uploaded file."
DEALS_TEXT_USER_PROMPT_PREFIX = (
    "Extract only deals and coupons from the text below. "
    "Ignore headers, footers, navigation, and unrelated site chrome.\n\n"
)


class LLMClientError(Exception):
    """Base exception for LLM client failures."""


class MissingGeminiDependencyError(LLMClientError):
    """Raised when google-generativeai is not installed."""


class GeminiConfigurationError(LLMClientError):
    """Raised when Gemini configuration is invalid."""


class GeminiResponseError(LLMClientError):
    """Raised when Gemini returns an unusable response."""


def _load_genai_module() -> object:
    try:
        return importlib.import_module("google.generativeai")
    except ImportError as exc:  # pragma: no cover - handled at runtime.
        raise MissingGeminiDependencyError(
            "google-generativeai is not installed. Add it to your environment first."
        ) from exc


def _extract_response_text(response: object) -> str:
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return ""

    chunks: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if content is None:
            continue

        parts = getattr(content, "parts", None) or ()
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)

    return "\n".join(chunks).strip()


def extract_deals_and_coupons_from_file(
    input_text_file: Path,
    output_text_file: Path,
    api_key: str,
    model_name: str = DEFAULT_GEMINI_MODEL,
) -> str:
    """Upload a .txt file to Gemini and save deals/coupons-only output to disk."""
    genai = _load_genai_module()

    normalized_api_key = api_key.strip()
    if not normalized_api_key:
        raise GeminiConfigurationError(
            "Missing GEMINI_API_KEY. Set it in your environment or .env file."
        )

    input_path = input_text_file.expanduser().resolve()
    if not input_path.exists() or not input_path.is_file():
        raise GeminiConfigurationError(f"Input text file not found: {input_path}")

    genai.configure(api_key=normalized_api_key)

    uploaded_file = genai.upload_file(path=str(input_path), mime_type="text/plain")
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=DEALS_SYSTEM_PROMPT,
    )

    response = model.generate_content([uploaded_file, DEALS_USER_PROMPT])

    response_text = (getattr(response, "text", "") or "").strip()
    if not response_text:
        response_text = _extract_response_text(response)

    if not response_text:
        raise GeminiResponseError("Gemini returned an empty response.")

    output_path = output_text_file.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(response_text + "\n", encoding="utf-8")

    return response_text


def extract_deals_and_coupons_from_text(
    text: str,
    api_key: str,
    model_name: str = DEFAULT_GEMINI_MODEL,
) -> str:
    """Send plain text to Gemini and return deals/coupons-only output."""
    genai = _load_genai_module()

    normalized_api_key = api_key.strip()
    if not normalized_api_key:
        raise GeminiConfigurationError(
            "Missing GEMINI_API_KEY. Set it in your environment or .env file."
        )

    normalized_text = text.strip()
    if not normalized_text:
        raise GeminiConfigurationError("Cannot send empty text to Gemini.")

    genai.configure(api_key=normalized_api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=DEALS_SYSTEM_PROMPT,
    )
    response = model.generate_content(
        DEALS_TEXT_USER_PROMPT_PREFIX + normalized_text
    )

    response_text = (getattr(response, "text", "") or "").strip()
    if not response_text:
        response_text = _extract_response_text(response)

    if not response_text:
        raise GeminiResponseError("Gemini returned an empty response.")

    return response_text
