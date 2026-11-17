"""The tests import the program from app/ and the developer tools from tools/, so they run from the project folder:
    python -m unittest"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in ("app", "tools"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)
