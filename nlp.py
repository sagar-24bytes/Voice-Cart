"""
nlp.py — Rule-Based NLP Intent & Entity Parser for VoiceCart.

Pure Python, zero ML dependencies.  Parses free-form shopping commands
into structured ParsedCommand dicts.

Design philosophy
-----------------
* Keyword synonym sets per intent make it trivial to extend new phrases
  or languages — just add strings to the relevant list.
* Number-word normalisation converts "two bottles" → "2 bottles" before
  quantity extraction.
* Language-specific prefixes (Hindi/Spanish) are checked first; English
  is the universal fallback.
* A confidence score lets callers decide whether to ask for clarification.

Extending
---------
To add a new language, append native-language keywords to ADD_KEYWORDS,
REMOVE_KEYWORDS, etc.  No other changes needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data class for parsed result
# ---------------------------------------------------------------------------

@dataclass
class ParsedCommand:
    intent: str                        # ADD | REMOVE | SEARCH | MODIFY_QUANTITY | UNKNOWN
    item_name: str                     # cleaned item name
    quantity: float = 1.0
    unit: str = "pcs"
    brand: Optional[str] = None
    price_max: Optional[float] = None  # parsed from "under $5"
    organic: bool = False
    confidence: float = 0.5
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Intent keyword sets  (extend freely)
# ---------------------------------------------------------------------------

ADD_KEYWORDS: list[str] = [
    # English
    "add", "buy", "purchase", "get", "grab", "pick up", "pick-up",
    "i need", "we need", "need", "i want", "we want", "want",
    "i'd like", "i would like", "please add", "can you add",
    "put on my list", "put on the list", "add to my list", "add to list",
    "put in cart", "add to cart", "get me", "bring me",
    # Hindi transliterations (common SpeechRecognition output for Hindi speakers)
    "jodo", "add karo", "chahiye", "lena hai", "le aao",
    "daalo", "list mein daalo", "khareedna hai",
    # Spanish
    "añadir", "agregar", "comprar", "necesito", "quiero", "pon",
    "añade", "agrega", "ponme", "dame",
    # French
    "ajouter", "acheter", "j'ai besoin", "mettre", "mets",
]

REMOVE_KEYWORDS: list[str] = [
    # English
    "remove", "delete", "take off", "take out", "drop", "cancel",
    "don't need", "do not need", "no longer need", "i don't need",
    "i don't want", "remove from", "delete from", "scratch off",
    "cross off", "forget", "nevermind", "ignore",
    # Hindi
    "hatao", "nikalo", "nahi chahiye", "remove karo", "delete karo",
    # Spanish
    "quitar", "eliminar", "borrar", "sacar", "no quiero", "no necesito",
    # French
    "enlever", "supprimer", "retirer",
]

SEARCH_KEYWORDS: list[str] = [
    # English
    "find", "search", "search for", "look for", "show me", "show",
    "browse", "where is", "do you have", "check for", "look up",
    "what about", "is there",
    # Hindi
    "dhundho", "khojo", "dikhao",
    # Spanish
    "buscar", "busca", "encuentra", "mostrar",
    # French
    "chercher", "trouve", "montrer",
]

MODIFY_KEYWORDS: list[str] = [
    "change", "update", "modify", "set", "make it", "change to",
    "update quantity", "change quantity", "set quantity",
    "cambiar", "changer", "modifier",
]

# ---------------------------------------------------------------------------
# Number-word → digit normalisation
# ---------------------------------------------------------------------------

NUMBER_WORDS: dict[str, float] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20,
    "half": 0.5, "a dozen": 12, "dozen": 12, "couple": 2, "few": 3,
    # Hindi numbers (Latin transliterations)
    "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5,
    "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
}

# ---------------------------------------------------------------------------
# Unit aliases → canonical unit
# ---------------------------------------------------------------------------

UNIT_ALIASES: dict[str, str] = {
    # Volume
    "bottle": "bottles", "bottles": "bottles", "btl": "bottles",
    "liter": "liters", "liters": "liters", "litre": "liters", "litres": "liters",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "gallon": "gallons", "gallons": "gallons",
    "cup": "cups", "cups": "cups",
    # Weight
    "kg": "kg", "kilogram": "kg", "kilograms": "kg", "kilo": "kg",
    "g": "g", "gram": "g", "grams": "g",
    "lb": "lbs", "lbs": "lbs", "pound": "lbs", "pounds": "lbs",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    # Count
    "piece": "pcs", "pieces": "pcs", "pcs": "pcs", "pc": "pcs",
    "pack": "packs", "packs": "packs", "packet": "packs", "packets": "packs",
    "box": "boxes", "boxes": "boxes",
    "can": "cans", "cans": "cans", "tin": "cans", "tins": "cans",
    "bag": "bags", "bags": "bags",
    "bunch": "bunches", "bunches": "bunches",
    "dozen": "dozen", "loaf": "loaf", "loaves": "loaf",
    "slice": "slices", "slices": "slices",
    "jar": "jars", "jars": "jars",
    "tube": "tubes", "tubes": "tubes",
    "roll": "rolls", "rolls": "rolls",
}

# Words that signal an organic/natural preference
ORGANIC_SIGNALS: list[str] = [
    "organic", "natural", "fresh", "raw", "farm", "bio",
]

# Filler words to strip from the final item name
FILLER_WORDS: set[str] = {
    "of", "the", "a", "an", "some", "any", "my", "me",
    "please", "for", "and", "to", "on", "in",
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace, remove non-essential punctuation."""
    text = text.lower()
    text = re.sub(r"[^\w\s$.,'\-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _replace_number_words(text: str) -> str:
    """Replace number-words with their digit equivalents."""
    # Sort longest-first so "a dozen" is matched before "dozen"
    sorted_words = sorted(NUMBER_WORDS.keys(), key=len, reverse=True)
    for word in sorted_words:
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        text = pattern.sub(str(int(NUMBER_WORDS[word]))
                           if NUMBER_WORDS[word] == int(NUMBER_WORDS[word])
                           else str(NUMBER_WORDS[word]), text)
    return text


def _extract_price(text: str) -> Optional[float]:
    """Extract a max-price constraint (e.g. 'under $5' → 5.0)."""
    patterns = [
        r"under\s+\$?(\d+(?:\.\d{1,2})?)",
        r"below\s+\$?(\d+(?:\.\d{1,2})?)",
        r"less\s+than\s+\$?(\d+(?:\.\d{1,2})?)",
        r"cheaper\s+than\s+\$?(\d+(?:\.\d{1,2})?)",
        r"max(?:imum)?\s+\$?(\d+(?:\.\d{1,2})?)",
        r"\$(\d+(?:\.\d{1,2})?)\s+or\s+(?:less|under|below)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def _remove_price_phrases(text: str) -> str:
    """Strip price-related sub-phrases so they don't bleed into item name."""
    phrases = [
        r"under\s+\$?\d+(?:\.\d+)?",
        r"below\s+\$?\d+(?:\.\d+)?",
        r"less\s+than\s+\$?\d+(?:\.\d+)?",
        r"cheaper\s+than\s+\$?\d+(?:\.\d+)?",
        r"max(?:imum)?\s+\$?\d+(?:\.\d+)?",
        r"\$\d+(?:\.\d+)?\s+or\s+(?:less|under|below)",
        r"\$\d+(?:\.\d+)?",
    ]
    for pat in phrases:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _extract_quantity_and_unit(text: str) -> tuple[float, str, str]:
    """
    Extract leading quantity + optional unit from text.
    Returns (quantity, unit, remaining_text).
    """
    # Match patterns like "2 kg", "2kg", "2 bottles of", "3.5 liters"
    m = re.match(
        r"^(\d+(?:\.\d+)?)\s*([a-z]+(?:\s+of)?)?",
        text.strip(),
    )
    if not m:
        return 1.0, "pcs", text

    qty = float(m.group(1))
    raw_unit = (m.group(2) or "").replace("of", "").strip()
    canonical_unit = UNIT_ALIASES.get(raw_unit, "pcs" if not raw_unit else raw_unit)
    remaining = text[m.end():].strip()
    return qty, canonical_unit, remaining


def _strip_intent_prefix(text: str, keywords: list[str]) -> str:
    """Remove the matched intent verb phrase from the start of text."""
    for kw in sorted(keywords, key=len, reverse=True):
        if text.startswith(kw):
            return text[len(kw):].strip()
    return text


def _detect_intent(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword appears in the text."""
    for kw in keywords:
        pattern = re.compile(
            r"(^|\s)" + re.escape(kw) + r"(\s|$)", re.IGNORECASE
        )
        if pattern.search(text):
            return True
    return False


def _clean_item_name(text: str) -> str:
    """Remove filler words and tidy up the final item name."""
    tokens = text.split()
    tokens = [t for t in tokens if t.lower() not in FILLER_WORDS]
    name = " ".join(tokens).strip(" '\"")
    # Title-case
    return name.title() if name else text.title()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_command(raw_text: str) -> ParsedCommand:
    """
    Parse a raw voice transcript into a structured ParsedCommand.

    Parameters
    ----------
    raw_text : str
        The text string produced by SpeechRecognition.

    Returns
    -------
    ParsedCommand
        Structured command with intent, item_name, quantity, unit, etc.
        Falls back to intent=UNKNOWN if no intent can be identified.
    """
    norm = _normalise(raw_text)
    with_digits = _replace_number_words(norm)

    price_max = _extract_price(with_digits)
    organic = any(s in with_digits for s in ORGANIC_SIGNALS)

    # Detect intent — most specific first
    intent = "UNKNOWN"
    stripped = with_digits

    if _detect_intent(with_digits, MODIFY_KEYWORDS):
        intent = "MODIFY_QUANTITY"
        stripped = _strip_intent_prefix(with_digits, MODIFY_KEYWORDS)
    elif _detect_intent(with_digits, REMOVE_KEYWORDS):
        intent = "REMOVE"
        stripped = _strip_intent_prefix(with_digits, REMOVE_KEYWORDS)
    elif _detect_intent(with_digits, SEARCH_KEYWORDS):
        intent = "SEARCH"
        stripped = _strip_intent_prefix(with_digits, SEARCH_KEYWORDS)
    elif _detect_intent(with_digits, ADD_KEYWORDS):
        intent = "ADD"
        stripped = _strip_intent_prefix(with_digits, ADD_KEYWORDS)

    # Remove price sub-phrases before parsing item name
    stripped = _remove_price_phrases(stripped)

    # Remove organic signal words so they don't appear in item name
    for sig in ORGANIC_SIGNALS:
        stripped = re.sub(r"\b" + re.escape(sig) + r"\b", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip()

    # Extract quantity + unit
    quantity, unit, remaining = _extract_quantity_and_unit(stripped)

    # Clean up item name
    item_name = _clean_item_name(remaining) if remaining else _clean_item_name(raw_text)

    confidence = 0.1 if intent == "UNKNOWN" else (0.85 if len(item_name) > 1 else 0.5)

    return ParsedCommand(
        intent=intent,
        item_name=item_name,
        quantity=quantity,
        unit=unit,
        price_max=price_max,
        organic=organic,
        confidence=confidence,
        raw_text=raw_text,
    )
