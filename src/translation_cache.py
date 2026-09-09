import os
import json
from google.genai import types
from pdf_extractor import client  # reuse the SAME Gemini client already set up there
from cedex_converter import translate_for_display

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_DIR = os.path.join(BASE_DIR, "mappings")
CACHE_FILE = os.path.join(MAPPINGS_DIR, "translation_cache.json")

# Ensure the cache file exists
if not os.path.exists(CACHE_FILE):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)


def _read_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _has_cyrillic(text):
    """True if any Cyrillic characters remain (i.e. the offline glossary
    didn't fully translate the text)."""
    return any('\u0400' <= ch <= '\u04FF' for ch in str(text))


def _call_gemini_translate(text):
    """One-off Gemini call for a phrase not covered by the glossary or cache.
    Returns None on any failure so the caller can fall back gracefully -
    never raises, never crashes the human-review prompt."""
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[
                text,
                "Translate this container repair job description from Russian "
                "to English. This is a shipping-container damage/repair report - "
                "keep the translation short, literal, and technical. Preserve "
                "any numbers, codes, or measurements exactly as written. "
                "Return ONLY the translated text - no quotes, no explanation, "
                "no extra commentary.",
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        translated = (response.text or "").strip()
        return translated if translated else None
    except Exception as e:
        print(f"  -> Translation API call failed ({e}); using partial offline translation instead.")
        return None


def translate_job_description(text):
    """
    Robust, low-dependency translation for TERMINAL DISPLAY ONLY.
    Never modifies the original job_description used for classification,
    matching, or Excel output - call this only where text is being printed
    for a human to read.

    Order of operations (cheapest/fastest first):
      1. Offline glossary (cedex_converter.translate_for_display) - instant, free.
         If this fully resolves the text (no Cyrillic left), return immediately.
      2. Persistent disk cache (mappings/translation_cache.json), keyed by the
         EXACT original text - instant, free, survives across runs and restarts.
      3. Gemini API call, ONLY on a genuine cache miss. The result is saved to
         the cache immediately, so this exact phrase never needs an API call again.
      4. If the API call fails for any reason, fall back to the partial
         glossary translation rather than crashing or blocking the review.
    """
    if not text:
        return text

    raw = str(text)

    # Step 1: offline glossary pass
    glossary_result = translate_for_display(raw)
    if not _has_cyrillic(glossary_result):
        return glossary_result  # fully resolved for free, no cache/API needed

    # Step 2: check the persistent cache, keyed on the ORIGINAL raw text
    cache = _read_cache()
    if raw in cache:
        return cache[raw]

    # Step 3: genuine cache miss - call Gemini once
    api_result = _call_gemini_translate(raw)

    if api_result:
        cache[raw] = api_result
        _write_cache(cache)
        print(f"  -> Saved new translation to cache (no API call needed for this phrase again).")
        return api_result

    # Step 4: API failed - degrade gracefully instead of blocking review
    return glossary_result
