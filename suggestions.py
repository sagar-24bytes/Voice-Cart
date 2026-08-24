"""
suggestions.py — Smart Suggestions Engine for VoiceCart.

Generates three types of actionable, locally-computed suggestions:

  1. History-based  — frequently added items currently missing from the list
  2. Seasonal       — items whose season[] list matches the current month
  3. Substitute     — alternatives when a catalog item is out of stock

All logic is pure Python; no external services or ML models required.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Load product catalog once at module import
# ---------------------------------------------------------------------------

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "data", "products.json")

def _load_catalog() -> list[dict]:
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)

CATALOG: list[dict] = _load_catalog()
_CATALOG_BY_ID: dict[str, dict] = {p["id"]: p for p in CATALOG}
_CATALOG_BY_NAME: dict[str, dict] = {p["name"].lower(): p for p in CATALOG}


# ---------------------------------------------------------------------------
# Season helpers
# ---------------------------------------------------------------------------

_MONTH_SEASON: dict[int, str] = {
    0: "winter", 1: "winter", 2: "spring",
    3: "spring", 4: "spring", 5: "summer",
    6: "summer", 7: "summer", 8: "fall",
    9: "fall",  10: "winter", 11: "winter",
}


def get_current_season() -> str:
    """Return the current season name based on the local month."""
    return _MONTH_SEASON.get(datetime.now().month - 1, "all")


# ---------------------------------------------------------------------------
# Data class for a suggestion
# ---------------------------------------------------------------------------

@dataclass
class Suggestion:
    key: str              # unique key for dismissal tracking
    suggestion_type: str  # "history" | "seasonal" | "substitute"
    product_name: str
    reason: str
    product_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Individual suggestion generators
# ---------------------------------------------------------------------------

def get_history_suggestions(
    add_history: dict[str, int],
    current_item_names: set[str],
    max_results: int = 4,
) -> list[Suggestion]:
    """
    Surface frequently-bought items that are missing from the current list.

    An item qualifies if it has been added ≥ 2 times historically and
    is not currently on the shopping list.
    """
    suggestions: list[Suggestion] = []
    # Sort by frequency descending
    sorted_history = sorted(
        add_history.items(), key=lambda kv: kv[1], reverse=True
    )
    for name, count in sorted_history:
        if count >= 2 and name.lower() not in current_item_names:
            product = _CATALOG_BY_NAME.get(name.lower())
            suggestions.append(
                Suggestion(
                    key=f"history:{name.lower()}",
                    suggestion_type="history",
                    product_name=name,
                    reason=f"You've added **{name}** {count}× before — running low?",
                    product_id=product["id"] if product else None,
                )
            )
        if len(suggestions) >= max_results:
            break
    return suggestions


def get_seasonal_suggestions(
    current_item_names: set[str],
    max_results: int = 3,
) -> list[Suggestion]:
    """
    Suggest in-season products not already on the shopping list.
    Only products whose season[] *specifically* includes the current season
    are shown (not 'all' — those are always available and less interesting).
    """
    season = get_current_season()
    suggestions: list[Suggestion] = []
    for product in CATALOG:
        if product["name"].lower() in current_item_names:
            continue
        if season in product.get("season", []):
            suggestions.append(
                Suggestion(
                    key=f"seasonal:{product['id']}",
                    suggestion_type="seasonal",
                    product_name=product["name"],
                    reason=(
                        f"**{product['name']}** is in season right now "
                        f"({season.capitalize()}) — great time to stock up! 🌿"
                    ),
                    product_id=product["id"],
                )
            )
        if len(suggestions) >= max_results:
            break
    return suggestions


def get_substitute_suggestions(
    current_item_names: set[str],
) -> list[Suggestion]:
    """
    For any item on the list that is marked out_of_stock in the catalog,
    recommend its substitutes.
    """
    suggestions: list[Suggestion] = []
    seen_sub_ids: set[str] = set()

    for name in current_item_names:
        product = _CATALOG_BY_NAME.get(name)
        if not product:
            continue
        if product.get("out_of_stock") and product.get("substitutes"):
            for sub_id in product["substitutes"][:2]:
                if sub_id in seen_sub_ids:
                    continue
                sub = _CATALOG_BY_ID.get(sub_id)
                if sub:
                    suggestions.append(
                        Suggestion(
                            key=f"substitute:{product['id']}:{sub_id}",
                            suggestion_type="substitute",
                            product_name=sub["name"],
                            reason=(
                                f"**{product['name']}** is out of stock — "
                                f"try **{sub['name']}** instead."
                            ),
                            product_id=sub_id,
                        )
                    )
                    seen_sub_ids.add(sub_id)
    return suggestions[:4]


# ---------------------------------------------------------------------------
# Master function
# ---------------------------------------------------------------------------

def get_all_suggestions(
    add_history: dict[str, int],
    current_items: list[dict],
    dismissed_keys: set[str],
) -> list[Suggestion]:
    """
    Collect, deduplicate, and filter out dismissed suggestions.

    Parameters
    ----------
    add_history     : {item_name: add_count} from the DB
    current_items   : active shopping list rows from the DB
    dismissed_keys  : set of suggestion keys the user has dismissed

    Returns
    -------
    list[Suggestion] — ordered: substitutes → history → seasonal
    """
    current_names = {item["name"].lower() for item in current_items}

    all_suggestions = (
        get_substitute_suggestions(current_names)
        + get_history_suggestions(add_history, current_names)
        + get_seasonal_suggestions(current_names)
    )

    # Deduplicate by product_name (case-insensitive)
    seen_names: set[str] = set()
    deduped: list[Suggestion] = []
    for s in all_suggestions:
        key = s.product_name.lower()
        if key not in seen_names:
            seen_names.add(key)
            deduped.append(s)

    # Filter out dismissed suggestions
    return [s for s in deduped if s.key not in dismissed_keys]


# ---------------------------------------------------------------------------
# Utility — categorise an item name against the catalog
# ---------------------------------------------------------------------------

def categorise_item(name: str) -> str:
    """
    Return the catalog category for an item name.
    Tries exact match, then startsWith, then includes.
    Falls back to 'Other' for unrecognised items.
    """
    lc = name.lower()
    # Exact
    if lc in _CATALOG_BY_NAME:
        return _CATALOG_BY_NAME[lc]["category"]
    # Starts-with
    for cname, product in _CATALOG_BY_NAME.items():
        if cname.startswith(lc) or lc.startswith(cname):
            return product["category"]
    # Contains
    for cname, product in _CATALOG_BY_NAME.items():
        if lc in cname or cname in lc:
            return product["category"]
    return "Other"


def search_catalog(
    query: str,
    price_max: Optional[float] = None,
    organic_only: bool = False,
) -> list[dict]:
    """
    Search the product catalog by name/tags and optional price filter.

    Parameters
    ----------
    query      : search string (matched against name and tags)
    price_max  : if set, only return products with avg_price <= price_max
    organic_only : if True, only return products with 'organic' in tags

    Returns
    -------
    List of matching product dicts.
    """
    lc_query = query.lower().strip()
    results: list[dict] = []

    for product in CATALOG:
        # Name or tag match
        name_match = lc_query in product["name"].lower()
        tag_match  = any(lc_query in tag for tag in product.get("tags", []))
        if not (name_match or tag_match):
            continue
        # Price filter
        if price_max is not None and product.get("avg_price", 0) > price_max:
            continue
        # Organic filter
        if organic_only and "organic" not in product.get("tags", []):
            continue
        results.append(product)

    return results
