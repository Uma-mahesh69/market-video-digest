"""The shared engine: it does the reading for every user at once.

Each run it finds the new videos on the channels in cloud/sources.json, has Gemini watch each one ONCE, fetches prices
and Wall Street's ratings, and writes one "card" per stock (signal, confidence, numbers) to Firestore. The web app only
reads those cards, so a user needs no keys and waits for nothing. Run it with:  python -m cloud.engine

It reuses the tested code in app/ (the notes format, the scoring of calls, the signal), which is why app/ is on the path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CLOUD = ROOT / "cloud"
if str(ROOT / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "app"))
