# 🛒 VoiceCart — Voice-Powered Smart Shopping Assistant

VoiceCart is a voice-driven shopping assistant built with Python and Streamlit that uses NLP to understand shopping commands, manage and categorize shopping lists, search products, and provide smart suggestions based on purchase history, seasonality, and available substitutes.

---
## 🌐 Live Application

**Working Application:** https://voice-cartsc.streamlit.app/

> Open the application in Chrome or Edge for the best voice-input experience.

## ✨ Features

| Feature | Details |
|---|---|
| 🎤 Voice input | `st.audio_input` → Google Speech API (free, no key) |
| 🌐 4 languages | English, Hindi, Spanish, French |
| 🧠 NLP parser | Rule-based -> handles 30+ phrasings per intent |
| 💡 Smart suggestions | History-based, seasonal, and substitute recommendations |
| 📋 Shopping list | Auto-categorised, grouped by aisle, with ± controls |
| 🔍 Catalog search | Voice + text + price slider + organic filter |
| 💾 Persistence | SQLite |
| 🚀 Deploy | Streamlit Community Cloud |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- pip

### Install & Run

```bash
# Clone or download the project
cd VoiceCart

# (Recommended) create a virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```


> **Microphone note:** Use Chrome or Edge for best mic support. Firefox may block `st.audio_input` in some configurations.

---

## 🗂️ Project Structure

```
VoiceCart/
├── app.py              ← Main Streamlit entrypoint (UI + voice pipeline)
├── nlp.py              ← Rule-based intent/entity parser
├── suggestions.py      ← Smart suggestions engine
├── db.py               ← SQLite helpers (list + history persistence)
├── data/
│   └── products.json   ← 90+ product catalog entries
├── requirements.txt
├── README.md
├── WRITEUP.md
└── .gitignore
```

---

## 🏛️ Architecture Overview

```
Browser mic
    │
    ▼
st.audio_input (WAV bytes)
    │
    ▼  [speech_recognition.recognize_google]
Transcript (plain text)
    │
    ▼  [nlp.parse_command()]
ParsedCommand {intent, item_name, quantity, unit, price_max, organic}
    │
    ├─ ADD          → db.add_item() → categorised list
    ├─ REMOVE       → db.remove_item()
    ├─ MODIFY_QTY   → db.update_quantity()
    └─ SEARCH       → suggestions.search_catalog() → Search tab
    
                       ┌──────────────────────┐
                       │  suggestions.py       │
                       │  · history-based      │
                       │  · seasonal           │
                       │  · substitutes        │
                       └──────────────────────┘
                                │
                       SQLite (db.py)
```

---

## 🧠 How the NLP Parser Works (`nlp.py`)

The parser is **purely rule-based** — no ML, no paid API.

1. **Normalise** — lowercase, collapse whitespace, strip punctuation  
2. **Replace number-words** — "two" → 2, "dozen" → 12, "paanch" → 5  
3. **Detect intent** — scan for keyword synonyms in priority order:  
   `MODIFY_QUANTITY` → `REMOVE` → `SEARCH` → `ADD` → `UNKNOWN`  
4. **Strip intent prefix** — remove the matched verb phrase  
5. **Extract price constraint** — regex patterns like `under $5`, `below 3 dollars`  
6. **Extract quantity + unit** — leading digit + unit alias (`2 kg`, `3 bottles of`)  
7. **Clean item name** — remove filler words, title-case  

**Supported languages:** English (primary), Hindi transliterations, Spanish, French — extend by adding keywords to the lists in `nlp.py`.

**Example parses:**

| Input | Intent | Item | Qty | Unit |
|---|---|---|---|---|
| "add 2 bottles of milk" | ADD | Milk | 2 | bottles |
| "I need 500g of flour" | ADD | Flour | 500 | g |
| "remove eggs" | REMOVE | Eggs | — | — |
| "find toothpaste under $5" | SEARCH | Toothpaste | — | — |
| "chahiye 3 kg chawal" | ADD | Chawal | 3 | kg |
| "necesito leche" | ADD | Leche | 1 | pcs |

---

## 💡 How Suggestions Work (`suggestions.py`)

Three suggestion types, all computed locally from `data/products.json` and SQLite history:

### 1. History-based
If an item has been added **≥ 2 times** historically but is **not on the current list**, surface *"You've added X before — running low?"*

### 2. Seasonal
Cross-reference the current month → season, then surface catalog items whose `season[]` matches and aren't already on the list.  
Current month (August) = **Summer** → surfaces mangoes, strawberries, bell peppers, etc.

### 3. Substitute
If a catalog item is marked `"out_of_stock": true` and the user has it on their list, suggest its `substitutes[]` from the catalog.

---

## ⚠️ Known Limitations

| Limitation | Notes |
|---|---|
| **Ephemeral storage on Streamlit Cloud** | Streamlit Community Cloud's filesystem resets on every redeploy. The SQLite DB and shopping list data will be lost. For persistent storage, swap `db.py` for a hosted DB (e.g. Supabase free tier with `supabase-py`). |
| **`recognize_google` needs internet** | The free Google Speech API used here requires an outbound internet connection. It will fail gracefully in offline environments with a clear error message. |
| **Browser mic support** | `st.audio_input` works best in Chrome and Edge. Firefox may have issues depending on HTTPS settings. |
| **No real-time streaming** | Streamlit's execution model reruns the script on each interaction; true real-time audio streaming is not supported. |
| **Hindi/Spanish NLP** | Support is demonstrative — limited to common transliterations that SpeechRecognition produces for those languages. |


---

## 🛠️ Development Notes

- All dependencies listed in `requirements.txt` are strictly required - no extras.
- `pydub` handles audio format conversion if `st.audio_input` returns a non-WAV format (browser-dependent). It is listed as a dependency for reliability.
- To add a new language to the NLP parser, simply append native-language keywords to `ADD_KEYWORDS`, `REMOVE_KEYWORDS`, etc. in `nlp.py`.
- To add products to the catalog, edit `data/products.json` — no code changes needed.
