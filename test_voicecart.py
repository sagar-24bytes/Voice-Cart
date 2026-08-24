"""
test_voicecart.py — Automated test suite for VoiceCart components.
Run with:  python test_voicecart.py
"""
import sys
import traceback

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []

def check(name, fn):
    try:
        fn()
        results.append((PASS, name))
        print(f"  {PASS}  {name}")
    except Exception as e:
        results.append((FAIL, name))
        print(f"  {FAIL}  {name}")
        print(f"         → {e}")
        traceback.print_exc()

print("\n" + "="*60)
print("  VoiceCart — Component Test Suite")
print("="*60)

# ── 1. NLP Parser ──────────────────────────────────────────────
print("\n📌 NLP Parser (nlp.py)")

from nlp import parse_command, ParsedCommand

def test_nlp_add_simple():
    r = parse_command("add milk")
    assert r.intent == "ADD", f"Expected ADD, got {r.intent}"
    assert "milk" in r.item_name.lower(), f"item_name: {r.item_name}"

def test_nlp_add_with_quantity():
    r = parse_command("add 2 bottles of water")
    assert r.intent == "ADD"
    assert r.quantity == 2.0, f"qty={r.quantity}"
    assert r.unit == "bottles", f"unit={r.unit}"

def test_nlp_add_number_word():
    r = parse_command("buy three apples")
    assert r.intent == "ADD"
    assert r.quantity == 3.0, f"qty={r.quantity}"

def test_nlp_remove():
    r = parse_command("remove eggs")
    assert r.intent == "REMOVE", f"intent={r.intent}"

def test_nlp_search_with_price():
    r = parse_command("find toothpaste under $5")
    assert r.intent == "SEARCH", f"intent={r.intent}"
    assert r.price_max == 5.0, f"price_max={r.price_max}"

def test_nlp_modify():
    r = parse_command("change quantity of milk to 3")
    assert r.intent == "MODIFY_QUANTITY", f"intent={r.intent}"

def test_nlp_organic_flag():
    r = parse_command("I need organic apples")
    assert r.organic == True, f"organic={r.organic}"

def test_nlp_hindi():
    r = parse_command("chahiye 3 kg chawal")
    assert r.intent == "ADD", f"intent={r.intent}"
    assert r.quantity == 3.0, f"qty={r.quantity}"

def test_nlp_spanish():
    r = parse_command("necesito leche")
    assert r.intent == "ADD", f"intent={r.intent}"

def test_nlp_unknown():
    r = parse_command("blah blah something random xyz")
    assert r.intent == "UNKNOWN"

check("add milk (simple)", test_nlp_add_simple)
check("add 2 bottles of water (qty + unit)", test_nlp_add_with_quantity)
check("buy three apples (number-word)", test_nlp_add_number_word)
check("remove eggs", test_nlp_remove)
check("find toothpaste under $5 (search + price)", test_nlp_search_with_price)
check("change quantity (modify intent)", test_nlp_modify)
check("organic flag detection", test_nlp_organic_flag)
check("Hindi: 'chahiye 3 kg chawal'", test_nlp_hindi)
check("Spanish: 'necesito leche'", test_nlp_spanish)
check("unknown intent fallback", test_nlp_unknown)

# ── 2. Product Catalog ─────────────────────────────────────────
print("\n📌 Product Catalog (data/products.json)")

import json, os

def test_catalog_loads():
    path = os.path.join("data", "products.json")
    assert os.path.exists(path), "products.json not found"
    with open(path) as f:
        data = json.load(f)
    assert len(data) >= 50, f"Only {len(data)} products — expected ≥50"

def test_catalog_schema():
    path = os.path.join("data", "products.json")
    with open(path) as f:
        data = json.load(f)
    required = {"id", "name", "category", "season", "substitutes", "avg_price", "tags", "out_of_stock"}
    for p in data:
        missing = required - set(p.keys())
        assert not missing, f"Product {p.get('id','?')} missing fields: {missing}"

check("catalog file loads (≥50 products)", test_catalog_loads)
check("catalog schema (all required fields present)", test_catalog_schema)

# ── 3. Suggestions Engine ──────────────────────────────────────
print("\n📌 Suggestions Engine (suggestions.py)")

from suggestions import (
    categorise_item, search_catalog, get_history_suggestions,
    get_seasonal_suggestions, get_substitute_suggestions, get_all_suggestions,
    CATALOG
)

def test_categorise_known():
    cat = categorise_item("Milk")
    assert cat == "Dairy", f"Expected Dairy, got {cat}"

def test_categorise_unknown():
    cat = categorise_item("Xyz Unknown Thing 999")
    assert cat == "Other", f"Expected Other, got {cat}"

def test_search_basic():
    results = search_catalog("milk")
    assert len(results) > 0, "No results for 'milk'"

def test_search_price_filter():
    results = search_catalog("milk", price_max=4.0)
    for r in results:
        assert r["avg_price"] <= 4.0, f"{r['name']} price {r['avg_price']} exceeds $4"

def test_search_organic():
    results = search_catalog("apples", organic_only=True)
    for r in results:
        assert "organic" in r["tags"], f"{r['name']} is not tagged organic"

def test_history_suggestions():
    history = {"Milk": 5, "Eggs": 3, "Bread": 1}
    current = [{"name": "Milk"}]
    suggestions = get_history_suggestions(history, {i["name"].lower() for i in current})
    names = [s.product_name for s in suggestions]
    assert "Eggs" in names, f"Expected Eggs in suggestions, got: {names}"
    assert "Milk" not in names, "Milk is already on list — should not be suggested"

def test_seasonal_suggestions():
    suggestions = get_seasonal_suggestions(set())
    assert len(suggestions) >= 0  # may be 0 if nothing in season

def test_substitute_suggestions():
    # Temporarily mark milk as out_of_stock for this test
    milk = next(p for p in CATALOG if p["id"] == "milk")
    original = milk["out_of_stock"]
    milk["out_of_stock"] = True
    current_names = {"milk"}
    subs = get_substitute_suggestions(current_names)
    milk["out_of_stock"] = original
    # Should have suggested almond-milk or oat-milk
    assert len(subs) > 0, "No substitute suggestions when milk is out of stock"

def test_all_suggestions_deduplication():
    history = {"Eggs": 10, "Bread": 5, "Milk": 3}
    current = []
    dismissed = set()
    all_s = get_all_suggestions(history, current, dismissed)
    names = [s.product_name for s in all_s]
    assert len(names) == len(set(n.lower() for n in names)), "Duplicate suggestions found"

check("categorise known item (Milk → Dairy)", test_categorise_known)
check("categorise unknown item → Other", test_categorise_unknown)
check("search catalog for 'milk'", test_search_basic)
check("search with price_max filter", test_search_price_filter)
check("search with organic_only filter", test_search_organic)
check("history suggestions (exclude on-list items)", test_history_suggestions)
check("seasonal suggestions (no crash)", test_seasonal_suggestions)
check("substitute suggestions (out_of_stock item)", test_substitute_suggestions)
check("all_suggestions deduplication", test_all_suggestions_deduplication)

# ── 4. Database Layer ──────────────────────────────────────────
print("\n📌 Database Layer (db.py)")

import db as database
import uuid, time

# Use a temp DB for testing
TEST_DB = "voicecart_test.db"
original_db_path = database.DB_PATH
database.DB_PATH = TEST_DB

def test_db_init():
    database.init_db()

def test_db_add_and_get():
    database.init_db()
    item_id = str(uuid.uuid4())
    database.add_item(item_id, "Test Milk", 2.0, "bottles", "Dairy", added_at=int(time.time()*1000))
    items = database.get_all_items()
    assert any(i["id"] == item_id for i in items), "Item not found after add"

def test_db_update_quantity():
    database.init_db()
    item_id = str(uuid.uuid4())
    database.add_item(item_id, "Test Rice", 1.0, "kg", "Grains & Pasta", added_at=int(time.time()*1000))
    database.update_quantity(item_id, 5.0)
    items = database.get_all_items()
    item = next((i for i in items if i["id"] == item_id), None)
    assert item and item["quantity"] == 5.0, f"qty={item['quantity'] if item else 'not found'}"

def test_db_toggle_checked():
    database.init_db()
    item_id = str(uuid.uuid4())
    database.add_item(item_id, "Test Eggs", 1.0, "dozen", "Dairy", added_at=int(time.time()*1000))
    database.toggle_checked(item_id)
    items = database.get_all_items()
    item = next((i for i in items if i["id"] == item_id), None)
    assert item and item["checked"] == 1

def test_db_remove_item():
    database.init_db()
    item_id = str(uuid.uuid4())
    database.add_item(item_id, "To Delete", 1.0, "pcs", "Other", added_at=int(time.time()*1000))
    database.remove_item(item_id)
    items = database.get_all_items()
    assert not any(i["id"] == item_id for i in items)

def test_db_history():
    database.init_db()
    item_id = str(uuid.uuid4())
    database.add_item(item_id, "History Item", 1.0, "pcs", "Other", added_at=int(time.time()*1000))
    history = database.get_add_history()
    assert "History Item" in history, f"history keys: {list(history.keys())}"
    assert history["History Item"] >= 1

def test_db_dismiss_suggestion():
    database.init_db()
    database.dismiss_suggestion("test:suggestion:key")
    dismissed = database.get_dismissed_suggestions()
    assert "test:suggestion:key" in dismissed

def test_db_clear_all():
    database.init_db()
    database.clear_all_items()
    items = database.get_all_items()
    assert len(items) == 0

check("db.init_db() creates tables", test_db_init)
check("db.add_item() + get_all_items()", test_db_add_and_get)
check("db.update_quantity()", test_db_update_quantity)
check("db.toggle_checked()", test_db_toggle_checked)
check("db.remove_item()", test_db_remove_item)
check("add_history frequency counter", test_db_history)
check("dismiss_suggestion + get_dismissed", test_db_dismiss_suggestion)
check("clear_all_items()", test_db_clear_all)

# Restore original DB path & clean up test DB
database.DB_PATH = original_db_path
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

# ── 5. Import check for app.py ─────────────────────────────────
print("\n📌 App-level imports")

def test_streamlit_importable():
    import streamlit  # noqa
    assert streamlit.__version__

def test_speech_recognition_importable():
    import speech_recognition as sr  # noqa
    r = sr.Recognizer()
    assert r is not None

def test_pydub_importable():
    from pydub import AudioSegment  # noqa

check("streamlit importable (version check)", test_streamlit_importable)
check("SpeechRecognition importable", test_speech_recognition_importable)
check("pydub importable", test_pydub_importable)

# ── Summary ────────────────────────────────────────────────────
print("\n" + "="*60)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
print(f"  Results: {passed} passed, {failed} failed out of {len(results)} tests")
if failed > 0:
    print("\n  Failed tests:")
    for status, name in results:
        if status == FAIL:
            print(f"    • {name}")
print("="*60 + "\n")
sys.exit(0 if failed == 0 else 1)
