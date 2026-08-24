"""
db.py — SQLite persistence helpers for VoiceCart.

Provides a thin wrapper around Python's built-in sqlite3 module to:
  - Store the active shopping list (items, quantities, categories, etc.)
  - Track add-history (frequency counter per item name) for suggestions
  - Manage dismissed suggestion IDs so they don't resurface immediately

Note on Streamlit Cloud:
  Streamlit Community Cloud's filesystem is ephemeral — every time the app
  is redeployed the SQLite file is reset.  This is acceptable for a demo
  project; for production use a hosted DB (Supabase, PlanetScale, etc.).
"""

import sqlite3
import os
from typing import Optional

# Path to the SQLite file — sits next to this module in the project root
DB_PATH = os.path.join(os.path.dirname(__file__), "voicecart.db")


def _get_conn() -> sqlite3.Connection:
    """Open (or create) the SQLite database and return a connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn


def init_db() -> None:
    """Create tables if they do not already exist."""
    conn = _get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS shopping_items (
                id          TEXT    PRIMARY KEY,
                name        TEXT    NOT NULL,
                quantity    REAL    NOT NULL DEFAULT 1,
                unit        TEXT    NOT NULL DEFAULT 'pcs',
                category    TEXT    NOT NULL DEFAULT 'Other',
                brand       TEXT,
                price_max   REAL,
                organic     INTEGER NOT NULL DEFAULT 0,
                checked     INTEGER NOT NULL DEFAULT 0,
                added_at    INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS add_history (
                item_name   TEXT    PRIMARY KEY,
                add_count   INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS dismissed_suggestions (
                suggestion_key  TEXT    PRIMARY KEY
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Shopping list helpers
# ---------------------------------------------------------------------------

def add_item(
    item_id: str,
    name: str,
    quantity: float,
    unit: str,
    category: str,
    brand: Optional[str] = None,
    price_max: Optional[float] = None,
    organic: bool = False,
    added_at: int = 0,
) -> None:
    """Insert a new shopping item and increment its history counter."""
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO shopping_items
                (id, name, quantity, unit, category, brand, price_max, organic, checked, added_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (item_id, name, quantity, unit, category, brand, price_max, int(organic), added_at),
        )
        # Upsert history counter
        conn.execute(
            """
            INSERT INTO add_history (item_name, add_count)
            VALUES (?, 1)
            ON CONFLICT(item_name) DO UPDATE SET add_count = add_count + 1
            """,
            (name,),
        )
        conn.commit()
    finally:
        conn.close()


def remove_item(item_id: str) -> None:
    """Delete an item from the shopping list by its ID."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM shopping_items WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()


def update_quantity(item_id: str, new_quantity: float) -> None:
    """Update the quantity of an existing item."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE shopping_items SET quantity = ? WHERE id = ?",
            (max(1.0, new_quantity), item_id),
        )
        conn.commit()
    finally:
        conn.close()


def toggle_checked(item_id: str) -> None:
    """Flip the checked (ticked-off) state of an item."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE shopping_items SET checked = NOT checked WHERE id = ?",
            (item_id,),
        )
        conn.commit()
    finally:
        conn.close()


def clear_checked() -> None:
    """Remove all checked (bought) items from the list."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM shopping_items WHERE checked = 1")
        conn.commit()
    finally:
        conn.close()


def clear_all_items() -> None:
    """Remove every item from the active shopping list."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM shopping_items")
        conn.commit()
    finally:
        conn.close()


def get_all_items() -> list[dict]:
    """Return all active shopping list items as a list of dicts."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM shopping_items ORDER BY added_at ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def get_add_history() -> dict[str, int]:
    """Return {item_name: add_count} for all historically added items."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT item_name, add_count FROM add_history").fetchall()
        return {row["item_name"]: row["add_count"] for row in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dismissed suggestions helpers
# ---------------------------------------------------------------------------

def dismiss_suggestion(key: str) -> None:
    """Mark a suggestion key as dismissed."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO dismissed_suggestions (suggestion_key) VALUES (?)",
            (key,),
        )
        conn.commit()
    finally:
        conn.close()


def get_dismissed_suggestions() -> set[str]:
    """Return the set of all dismissed suggestion keys."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT suggestion_key FROM dismissed_suggestions"
        ).fetchall()
        return {row["suggestion_key"] for row in rows}
    finally:
        conn.close()


def clear_dismissed_suggestions() -> None:
    """Reset all dismissed suggestions (useful for testing)."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM dismissed_suggestions")
        conn.commit()
    finally:
        conn.close()
