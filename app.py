"""
app.py — VoiceCart: Voice Command Shopping Assistant
======================================================
Main Streamlit entrypoint.

Run locally:
    streamlit run app.py

Deploy to Streamlit Community Cloud:
    Push this repo to GitHub, then connect at share.streamlit.io — zero config.

Architecture
------------
  app.py        — UI, voice pipeline, routing between tabs
  nlp.py        — Rule-based intent/entity parser
  suggestions.py — Smart suggestion engine (history / seasonal / substitute)
  db.py         — SQLite persistence helpers
  data/products.json — Local product catalog
"""

from __future__ import annotations

import io
import time
import uuid
from typing import Optional

import streamlit as st

# Internal modules
import db
import nlp
import suggestions as sug

# ---------------------------------------------------------------------------
# Page config (must be the first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="VoiceCart — Voice Shopping Assistant",
    page_icon="🛒",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Initialise database on first run
# ---------------------------------------------------------------------------

db.init_db()

# ---------------------------------------------------------------------------
# Custom CSS — clean, mobile-first, premium feel
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* ── Google Font ─────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* ── App background ──────────────────────────────────── */
    .stApp { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); }

    /* ── Header ──────────────────────────────────────────── */
    .vc-header {
        text-align: center;
        padding: 1.5rem 0 0.5rem;
    }
    .vc-header h1 {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #34d399, #60a5fa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .vc-header p { color: #94a3b8; font-size: 0.95rem; margin: 0.25rem 0 0; }

    /* ── Transcript box ──────────────────────────────────── */
    .transcript-box {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 0.75rem 1rem;
        color: #e2e8f0;
        font-size: 0.95rem;
        min-height: 2.5rem;
        margin: 0.5rem 0;
    }
    .transcript-box .intent-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-left: 0.5rem;
    }
    .badge-add      { background:#064e3b; color:#34d399; }
    .badge-remove   { background:#450a0a; color:#f87171; }
    .badge-search   { background:#172554; color:#60a5fa; }
    .badge-modify   { background:#431407; color:#fb923c; }
    .badge-unknown  { background:#1e1b4b; color:#a78bfa; }

    /* ── Shopping list item card ─────────────────────────── */
    .item-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 0.6rem 0.9rem;
        margin-bottom: 0.4rem;
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    .item-card.checked { opacity: 0.45; text-decoration: line-through; }
    .item-name  { color: #f1f5f9; font-weight: 500; flex: 1; }
    .item-meta  { color: #64748b; font-size: 0.8rem; }
    .item-qty   { color: #34d399; font-weight: 600; font-size: 0.95rem; }

    /* ── Suggestion card ─────────────────────────────────── */
    .sug-card {
        background: linear-gradient(135deg, #0c2340, #0d2b1e);
        border: 1px solid #1e40af44;
        border-radius: 10px;
        padding: 0.65rem 1rem;
        margin-bottom: 0.4rem;
        color: #cbd5e1;
        font-size: 0.9rem;
    }
    .sug-icon { font-size: 1.1rem; margin-right: 0.4rem; }

    /* ── Section headings ─────────────────────────────────── */
    .section-title {
        color: #94a3b8;
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin: 1.2rem 0 0.4rem;
    }

    /* ── Divider ──────────────────────────────────────────── */
    .vc-divider { border-top: 1px solid #334155; margin: 1rem 0; }

    /* ── Empty state ──────────────────────────────────────── */
    .empty-state {
        text-align: center;
        padding: 2.5rem 1rem;
        color: #475569;
    }
    .empty-state .emoji { font-size: 3rem; }
    .empty-state p { margin: 0.5rem 0 0; font-size: 0.95rem; }

    /* ── Category header ─────────────────────────────────── */
    .cat-header {
        font-size: 0.8rem;
        font-weight: 600;
        color: #60a5fa;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        padding: 0.3rem 0;
        border-bottom: 1px solid #1e3a5f;
        margin-bottom: 0.35rem;
    }

    /* ── Hide Streamlit chrome ───────────────────────────── */
    #MainMenu, footer, header { visibility: hidden; }

    /* ── Sidebar ─────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: #0f172a;
        border-right: 1px solid #1e293b;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

def _init_session() -> None:
    defaults: dict = {
        "last_transcript": "",
        "last_command": None,
        "action_message": "",
        "search_query": "",
        "search_price_max": None,
        "search_organic": False,
        "audio_processed_key": None,   # tracks which audio blob we already processed
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

_init_session()

# ---------------------------------------------------------------------------
# Language configuration
# ---------------------------------------------------------------------------

LANGUAGES = {
    "🇺🇸 English":  "en-US",
    "🇮🇳 Hindi":    "hi-IN",
    "🇪🇸 Spanish":  "es-ES",
    "🇫🇷 French":   "fr-FR",
}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🛒 VoiceCart")
    st.markdown("---")

    selected_lang_label = st.selectbox(
        "🌐 Language",
        options=list(LANGUAGES.keys()),
        index=0,
        help="Sets the speech recognition language for voice input.",
    )
    lang_code = LANGUAGES[selected_lang_label]

    st.markdown("---")
    st.markdown("### ⚙️ List Actions")

    if st.button("✅ Clear Checked Items", use_container_width=True):
        db.clear_checked()
        st.toast("Checked items cleared!", icon="✅")
        st.rerun()

    if st.button("🗑️ Clear Entire List", use_container_width=True, type="secondary"):
        db.clear_all_items()
        st.toast("Shopping list cleared!", icon="🗑️")
        st.rerun()

    if st.button("🔄 Reset Suggestions", use_container_width=True):
        db.clear_dismissed_suggestions()
        st.toast("Suggestion history reset.", icon="🔄")
        st.rerun()

    st.markdown("---")
    st.markdown(
        "<small style='color:#475569;'>Voice recognition requires internet "
        "access (Google Speech API — free, no key needed).</small>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="vc-header">
        <h1>🛒 VoiceCart</h1>
        <p>Voice-Powered Smart Shopping Assistant</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Tab navigation
# ---------------------------------------------------------------------------

tab_list, tab_search = st.tabs(["📋 Shopping List", "🔍 Search Catalog"])

# ===========================================================================
# TAB 1 — Shopping List + Voice Input
# ===========================================================================

with tab_list:

    # -----------------------------------------------------------------------
    # Voice input section
    # -----------------------------------------------------------------------

    st.markdown('<p class="section-title">🎤 Voice Command</p>', unsafe_allow_html=True)

    audio_value = st.audio_input(
        "Tap to record your command",
        key="mic_input",
        help='Say things like "Add 2 bottles of milk", "Remove eggs", "I need bread"',
    )

    # Manual text fallback
    with st.expander("⌨️ Type a command instead"):
        typed_cmd = st.text_input(
            "Type your command",
            placeholder='e.g. "add 3 kg of rice" or "remove eggs"',
            label_visibility="collapsed",
        )
        run_typed = st.button("▶ Run Command", key="run_typed")

    # -----------------------------------------------------------------------
    # Process audio — only once per unique audio recording
    # -----------------------------------------------------------------------

    transcript_text: str = ""
    processing_error: str = ""

    if audio_value is not None:
        # Use the audio bytes as a cache key to avoid reprocessing on reruns
        audio_bytes = audio_value.read()
        audio_key = hash(audio_bytes)

        if audio_key != st.session_state.get("audio_processed_key"):
            st.session_state.audio_processed_key = audio_key

            with st.spinner("🎧 Transcribing your voice..."):
                try:
                    import speech_recognition as sr

                    recognizer = sr.Recognizer()

                    # st.audio_input returns a WAV-compatible bytes object
                    audio_io = io.BytesIO(audio_bytes)

                    # Try loading directly as WAV first
                    try:
                        with sr.AudioFile(audio_io) as source:
                            audio_data = recognizer.record(source)
                    except Exception:
                        # Fall back: use pydub to convert to WAV PCM
                        try:
                            from pydub import AudioSegment
                            audio_io.seek(0)
                            segment = AudioSegment.from_file(audio_io)
                            wav_io = io.BytesIO()
                            segment.export(wav_io, format="wav")
                            wav_io.seek(0)
                            with sr.AudioFile(wav_io) as source:
                                audio_data = recognizer.record(source)
                        except Exception as conv_err:
                            processing_error = (
                                f"Could not process audio format: {conv_err}. "
                                "Please try again."
                            )
                            audio_data = None  # type: ignore[assignment]

                    if audio_data:
                        transcript_text = recognizer.recognize_google(
                            audio_data, language=lang_code
                        )
                        st.session_state.last_transcript = transcript_text

                except sr.UnknownValueError:
                    processing_error = (
                        "🤔 Couldn't understand the audio. "
                        "Please speak clearly and try again."
                    )
                except sr.RequestError as e:
                    processing_error = (
                        f"🌐 Speech recognition service error: {e}. "
                        "Check your internet connection."
                    )
                except Exception as e:
                    processing_error = f"⚠️ Unexpected error: {e}"

    # Use typed command if provided
    if run_typed and typed_cmd.strip():
        transcript_text = typed_cmd.strip()
        st.session_state.last_transcript = transcript_text

    # -----------------------------------------------------------------------
    # Display transcript & parse intent
    # -----------------------------------------------------------------------

    if processing_error:
        st.error(processing_error)

    last_transcript = st.session_state.get("last_transcript", "")

    if last_transcript:
        badge_map = {
            "ADD":             ("badge-add",    "➕ ADD"),
            "REMOVE":          ("badge-remove", "🗑️ REMOVE"),
            "SEARCH":          ("badge-search", "🔍 SEARCH"),
            "MODIFY_QUANTITY": ("badge-modify", "✏️ MODIFY"),
            "UNKNOWN":         ("badge-unknown","❓ UNKNOWN"),
        }

        cmd: Optional[nlp.ParsedCommand] = None

        with st.spinner("🧠 Parsing command..."):
            try:
                cmd = nlp.parse_command(last_transcript)
            except Exception as parse_err:
                st.error(f"Parser error: {parse_err}")

        if cmd:
            badge_cls, badge_label = badge_map.get(
                cmd.intent, ("badge-unknown", "❓ UNKNOWN")
            )
            st.markdown(
                f"""
                <div class="transcript-box">
                    💬 <em>"{last_transcript}"</em>
                    <span class="intent-badge {badge_cls}">{badge_label}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # ---------------------------------------------------------------
            # Execute the parsed command
            # ---------------------------------------------------------------

            action_msg: str = ""

            if transcript_text:  # Only act on fresh input
                if cmd.intent == "ADD" and cmd.item_name:
                    category = sug.categorise_item(cmd.item_name)
                    item_id = str(uuid.uuid4())
                    db.add_item(
                        item_id=item_id,
                        name=cmd.item_name,
                        quantity=cmd.quantity,
                        unit=cmd.unit,
                        category=category,
                        price_max=cmd.price_max,
                        organic=cmd.organic,
                        added_at=int(time.time() * 1000),
                    )
                    action_msg = (
                        f"✅ Added **{cmd.quantity}× {cmd.item_name}** to **{category}**"
                        + (f" (under ${cmd.price_max:.0f})" if cmd.price_max else "")
                    )
                    st.toast(action_msg.replace("**", ""), icon="✅")

                elif cmd.intent == "REMOVE" and cmd.item_name:
                    items = db.get_all_items()
                    removed = False
                    for item in items:
                        if cmd.item_name.lower() in item["name"].lower():
                            db.remove_item(item["id"])
                            action_msg = f"🗑️ Removed **{item['name']}** from your list."
                            st.toast(action_msg.replace("**", ""), icon="🗑️")
                            removed = True
                            break
                    if not removed:
                        action_msg = f"⚠️ **{cmd.item_name}** not found on your list."

                elif cmd.intent == "SEARCH":
                    # Switch user to the search tab suggestion
                    action_msg = (
                        f"🔍 Showing search results for **{cmd.item_name}**"
                        + (f" under ${cmd.price_max:.0f}" if cmd.price_max else "")
                        + " — see the **Search Catalog** tab."
                    )
                    st.session_state.search_query = cmd.item_name
                    if cmd.price_max:
                        st.session_state.search_price_max = cmd.price_max
                    if cmd.organic:
                        st.session_state.search_organic = True

                elif cmd.intent == "MODIFY_QUANTITY" and cmd.item_name:
                    items = db.get_all_items()
                    modified = False
                    for item in items:
                        if cmd.item_name.lower() in item["name"].lower():
                            db.update_quantity(item["id"], cmd.quantity)
                            action_msg = (
                                f"✏️ Updated **{item['name']}** quantity to **{cmd.quantity} {cmd.unit}**."
                            )
                            st.toast(action_msg.replace("**", ""), icon="✏️")
                            modified = True
                            break
                    if not modified:
                        action_msg = f"⚠️ **{cmd.item_name}** not found — try adding it first."

                else:
                    action_msg = (
                        "🤷 Didn't quite catch what you want. "
                        "Try: *'add 2 litres of milk'* or *'remove eggs'*."
                    )

                st.session_state.action_message = action_msg

            # Show last action message
            if st.session_state.action_message:
                st.markdown(
                    f"<div style='background:#0f2d1f;border:1px solid #166534;"
                    f"border-radius:8px;padding:0.5rem 1rem;color:#bbf7d0;"
                    f"font-size:0.9rem;margin:0.4rem 0;'>"
                    f"{st.session_state.action_message}</div>",
                    unsafe_allow_html=True,
                )

    # -----------------------------------------------------------------------
    # Smart Suggestions
    # -----------------------------------------------------------------------

    st.markdown('<div class="vc-divider"></div>', unsafe_allow_html=True)
    st.markdown('<p class="section-title">💡 Smart Suggestions</p>', unsafe_allow_html=True)

    current_items = db.get_all_items()
    add_history   = db.get_add_history()
    dismissed     = db.get_dismissed_suggestions()

    all_suggestions = sug.get_all_suggestions(add_history, current_items, dismissed)

    if not all_suggestions:
        st.markdown(
            "<small style='color:#475569;'>No suggestions right now. "
            "Add a few items to get personalised recommendations.</small>",
            unsafe_allow_html=True,
        )
    else:
        type_icons = {"history": "🕓", "seasonal": "🌿", "substitute": "🔄"}
        for s in all_suggestions:
            icon = type_icons.get(s.suggestion_type, "💡")
            with st.container():
                col_text, col_accept, col_dismiss = st.columns([6, 2, 1.5])
                with col_text:
                    st.markdown(
                        f"<div class='sug-card'><span class='sug-icon'>{icon}</span>{s.reason}</div>",
                        unsafe_allow_html=True,
                    )
                with col_accept:
                    if st.button(
                        f"➕ Add", key=f"sug_accept_{s.key}", use_container_width=True
                    ):
                        category = sug.categorise_item(s.product_name)
                        db.add_item(
                            item_id=str(uuid.uuid4()),
                            name=s.product_name,
                            quantity=1,
                            unit="pcs",
                            category=category,
                            added_at=int(time.time() * 1000),
                        )
                        db.dismiss_suggestion(s.key)
                        st.toast(f"Added {s.product_name}!", icon="✅")
                        st.rerun()
                with col_dismiss:
                    if st.button(
                        "✕", key=f"sug_dismiss_{s.key}", use_container_width=True,
                        help="Dismiss this suggestion",
                    ):
                        db.dismiss_suggestion(s.key)
                        st.rerun()

    # -----------------------------------------------------------------------
    # Shopping List — grouped by category
    # -----------------------------------------------------------------------

    st.markdown('<div class="vc-divider"></div>', unsafe_allow_html=True)
    st.markdown('<p class="section-title">🛒 Your Shopping List</p>', unsafe_allow_html=True)

    # Refresh items (suggestions may have added)
    current_items = db.get_all_items()

    if not current_items:
        st.markdown(
            """
            <div class="empty-state">
                <div class="emoji">🛒</div>
                <p>Your list is empty.<br>
                <small>Record a voice command or type one above to get started.</small></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Group by category
        categories: dict[str, list[dict]] = {}
        for item in current_items:
            categories.setdefault(item["category"], []).append(item)

        # Sort categories alphabetically, "Other" last
        sorted_cats = sorted(
            categories.keys(),
            key=lambda c: ("zzz" if c == "Other" else c),
        )

        # Summary line
        total_items   = len(current_items)
        checked_count = sum(1 for i in current_items if i["checked"])
        st.markdown(
            f"<small style='color:#64748b;'>{total_items} item(s) · "
            f"{checked_count} checked</small>",
            unsafe_allow_html=True,
        )

        for cat in sorted_cats:
            items_in_cat = categories[cat]
            with st.expander(f"📦 {cat}  ({len(items_in_cat)})", expanded=True):
                for item in items_in_cat:
                    col_check, col_name, col_qty_ctrl, col_del = st.columns(
                        [0.5, 4.5, 3, 1]
                    )

                    with col_check:
                        checked = st.checkbox(
                            "",
                            value=bool(item["checked"]),
                            key=f"chk_{item['id']}",
                            label_visibility="collapsed",
                        )
                        if checked != bool(item["checked"]):
                            db.toggle_checked(item["id"])
                            st.rerun()

                    with col_name:
                        name_style = (
                            "text-decoration:line-through;color:#475569;"
                            if item["checked"]
                            else "color:#f1f5f9;"
                        )
                        badge_parts = []
                        if item.get("organic"):
                            badge_parts.append("🌿 Organic")
                        if item.get("price_max"):
                            badge_parts.append(f"under ${item['price_max']:.0f}")
                        badge_str = (
                            f"  <small style='color:#64748b;'>({', '.join(badge_parts)})</small>"
                            if badge_parts
                            else ""
                        )
                        st.markdown(
                            f"<span style='{name_style};font-weight:500;'>"
                            f"{item['name']}</span>{badge_str}",
                            unsafe_allow_html=True,
                        )

                    with col_qty_ctrl:
                        q_col1, q_col2, q_col3 = st.columns([1, 2, 1])
                        with q_col1:
                            if st.button(
                                "−", key=f"dec_{item['id']}", use_container_width=True
                            ):
                                db.update_quantity(item["id"], item["quantity"] - 1)
                                st.rerun()
                        with q_col2:
                            st.markdown(
                                f"<div style='text-align:center;color:#34d399;"
                                f"font-weight:600;padding-top:6px;'>"
                                f"{item['quantity']:g} {item['unit']}</div>",
                                unsafe_allow_html=True,
                            )
                        with q_col3:
                            if st.button(
                                "+", key=f"inc_{item['id']}", use_container_width=True
                            ):
                                db.update_quantity(item["id"], item["quantity"] + 1)
                                st.rerun()

                    with col_del:
                        if st.button(
                            "🗑", key=f"del_{item['id']}", use_container_width=True,
                            help=f"Remove {item['name']}",
                        ):
                            db.remove_item(item["id"])
                            st.toast(f"Removed {item['name']}", icon="🗑️")
                            st.rerun()

# ===========================================================================
# TAB 2 — Voice-Activated Catalog Search
# ===========================================================================

with tab_search:

    st.markdown('<p class="section-title">🔍 Search Product Catalog</p>', unsafe_allow_html=True)

    # Pre-fill from voice command if available
    search_default = st.session_state.get("search_query", "")

    # Voice input for search
    search_audio = st.audio_input(
        "Record a search command",
        key="search_mic",
        help='Say things like "find organic apples" or "toothpaste under $5"',
    )

    if search_audio is not None:
        search_audio_bytes = search_audio.read()
        search_audio_key = hash(search_audio_bytes)

        if search_audio_key != st.session_state.get("search_audio_key"):
            st.session_state.search_audio_key = search_audio_key

            with st.spinner("🎧 Transcribing search..."):
                try:
                    import speech_recognition as sr
                    recognizer = sr.Recognizer()
                    audio_io = io.BytesIO(search_audio_bytes)
                    try:
                        with sr.AudioFile(audio_io) as source:
                            audio_data = recognizer.record(source)
                    except Exception:
                        from pydub import AudioSegment
                        audio_io.seek(0)
                        segment = AudioSegment.from_file(audio_io)
                        wav_io = io.BytesIO()
                        segment.export(wav_io, format="wav")
                        wav_io.seek(0)
                        with sr.AudioFile(wav_io) as source:
                            audio_data = recognizer.record(source)

                    search_text = recognizer.recognize_google(
                        audio_data, language=lang_code
                    )
                    parsed = nlp.parse_command(search_text)
                    st.session_state.search_query = parsed.item_name
                    if parsed.price_max:
                        st.session_state.search_price_max = parsed.price_max
                    if parsed.organic:
                        st.session_state.search_organic = True
                    st.info(f'🎙️ Heard: *"{search_text}"*')

                except sr.UnknownValueError:
                    st.error("Couldn't understand the audio. Please try again.")
                except sr.RequestError as e:
                    st.error(f"Speech recognition error: {e}")
                except Exception as e:
                    st.error(f"Error: {e}")

    # Search controls
    col_q, col_organic = st.columns([5, 2])
    with col_q:
        query = st.text_input(
            "Search",
            value=st.session_state.get("search_query", ""),
            placeholder="e.g. apples, toothpaste, vegan...",
            label_visibility="collapsed",
        )
    with col_organic:
        organic_only = st.checkbox(
            "🌿 Organic only",
            value=st.session_state.get("search_organic", False),
        )

    price_max_search: Optional[float] = None
    price_slider = st.slider(
        "Max price ($)",
        min_value=0.0,
        max_value=20.0,
        value=float(st.session_state.get("search_price_max") or 20.0),
        step=0.5,
        format="$%.1f",
    )
    if price_slider < 20.0:
        price_max_search = price_slider

    # Run search
    if query.strip():
        results = sug.search_catalog(
            query=query.strip(),
            price_max=price_max_search,
            organic_only=organic_only,
        )

        if not results:
            st.markdown(
                """
                <div class="empty-state">
                    <div class="emoji">🔍</div>
                    <p>No products found matching your search.<br>
                    <small>Try a broader term or adjust the price filter.</small></p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<small style='color:#64748b;'>{len(results)} result(s) for "
                f"<strong style='color:#60a5fa;'>{query}</strong></small>",
                unsafe_allow_html=True,
            )

            # Group results by category
            cat_results: dict[str, list[dict]] = {}
            for p in results:
                cat_results.setdefault(p["category"], []).append(p)

            for cat, prods in sorted(cat_results.items()):
                st.markdown(f'<div class="cat-header">📦 {cat}</div>', unsafe_allow_html=True)
                for prod in prods:
                    r_col1, r_col2, r_col3 = st.columns([4, 2, 2])
                    with r_col1:
                        tags_html = " ".join(
                            f"<span style='background:#1e3a5f;color:#93c5fd;"
                            f"border-radius:4px;padding:1px 6px;font-size:0.7rem;'>{t}</span>"
                            for t in prod.get("tags", [])[:4]
                        )
                        oos_badge = (
                            "<span style='background:#450a0a;color:#f87171;"
                            "border-radius:4px;padding:1px 6px;font-size:0.7rem;"
                            "margin-left:4px;'>Out of Stock</span>"
                            if prod.get("out_of_stock")
                            else ""
                        )
                        st.markdown(
                            f"<div style='color:#f1f5f9;font-weight:500;'>{prod['name']}"
                            f"{oos_badge}</div>"
                            f"<div style='margin-top:4px;'>{tags_html}</div>",
                            unsafe_allow_html=True,
                        )
                    with r_col2:
                        season_str = ", ".join(
                            s.capitalize() for s in prod.get("season", [])
                            if s != "all"
                        ) or "Year-round"
                        st.markdown(
                            f"<div style='color:#34d399;font-weight:600;'>"
                            f"${prod['avg_price']:.2f}</div>"
                            f"<div style='color:#475569;font-size:0.78rem;'>{season_str}</div>",
                            unsafe_allow_html=True,
                        )
                    with r_col3:
                        if st.button(
                            "➕ Add to List",
                            key=f"add_search_{prod['id']}",
                            use_container_width=True,
                            disabled=bool(prod.get("out_of_stock")),
                        ):
                            db.add_item(
                                item_id=str(uuid.uuid4()),
                                name=prod["name"],
                                quantity=1,
                                unit="pcs",
                                category=prod["category"],
                                added_at=int(time.time() * 1000),
                            )
                            st.toast(f"Added {prod['name']} to your list!", icon="✅")
                            st.rerun()

                    st.markdown(
                        "<hr style='border:none;border-top:1px solid #1e293b;margin:0.3rem 0;'>",
                        unsafe_allow_html=True,
                    )
    else:
        st.markdown(
            "<div class='empty-state'><div class='emoji'>🔍</div>"
            "<p>Type or speak a product name to search the catalog.</p></div>",
            unsafe_allow_html=True,
        )
