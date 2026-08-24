# VoiceCart — Technical Approach Write-Up

VoiceCart is a voice-driven shopping assistant built on a deliberately minimal, fully free stack: Python, Streamlit, and SQLite.

**Why Streamlit?** It eliminates the need for a separate frontend entirely. `st.audio_input` provides native browser mic recording, and the Python-only architecture means a single `streamlit run app.py` command runs everything — no Node.js, no build step, no reverse proxy.

**Why `recognize_google` over local Whisper?** Streamlit Community Cloud's free tier limits RAM to ~1 GB. Loading a Whisper model (smallest: ~150 MB RAM + slow inference on CPU) would either crash the app or produce unacceptable latency. `recognize_google` offloads inference to Google's servers and returns results in under a second, with zero local compute cost. The trade-off is a required internet connection and Google's rate limits — acceptable for a demo.

**Why rule-based NLP over an LLM?** Rule-based parsing is instantaneous, deterministic, requires no API key, and is easy to inspect and extend. An LLM would add latency, cost, and a mandatory paid dependency. For shopping commands, the vocabulary is bounded enough that keyword synonym sets cover the vast majority of real phrasings.

**Why SQLite over a hosted DB?** Python's built-in `sqlite3` requires zero extra dependencies or credentials, making local setup a single `pip install` and deploy a single button click. The known trade-off — ephemeral storage on Streamlit Cloud — is documented clearly in the README.
