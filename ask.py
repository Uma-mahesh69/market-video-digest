"""Ask a question about the videos saved in ytmd; get an answer that cites its sources.

Usage (from the folder that contains the `ytmd` script):
    set GEMINI_API_KEY=your-key-here
    python ask.py "why can javascript handle io if it is single threaded?"
    python ask.py "what is the event loop" --video DHjqpvDnNGE --show-passages

Flow: question -> keywords -> ytmd search -> numbered passages -> Gemini -> checked citations.
Internal tooling only. Uses the Python standard library; no pip installs.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

YTMD = Path(__file__).resolve().parent / "ytmd"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
NOT_FOUND = "NOT_FOUND"

# Words that carry no search value. Removing them turns a question into keywords.
STOPWORDS = set("""
a an and are as at be been but by can could did do does for from had has have how i if in into is it
its me my of on or our should so than that the their them then there these they this to was we were
what when where which who why will with would you your about tell explain say said says does video
""".split())

SYSTEM_PROMPT = f"""You answer questions for an internal team using passages from video transcripts.

Rules:
1. Use ONLY the numbered passages below. Do not use outside knowledge, even if you know the answer.
2. After every claim, cite the passage it came from like [C1] or [C2].
3. If the passages do not contain the answer, reply with exactly {NOT_FOUND} and nothing else.
4. The passages are auto-generated captions: no punctuation, and names may be misspelled.
   Read through that, but do not invent details that are not there.
5. Answer in 1-4 plain sentences."""


def keywords(question: str) -> list[str]:
    """'Why can JS handle I/O?' -> ['js', 'handle']. Order kept, duplicates dropped."""
    words = re.findall(r"[a-z0-9]+", question.lower())
    kept = [w for w in words if w not in STOPWORDS and len(w) > 1]
    return list(dict.fromkeys(kept))[:12]


def search(words: list[str], top: int, video: str | None) -> list[dict]:
    """Run ytmd's keyword search. '--match any' ranks passages that hit more words higher."""
    cmd = [sys.executable, str(YTMD), "search", *words, "--match", "any", "-n", str(top), "--json"]
    if video:
        cmd += ["--video", video]
    # Windows gives a piped program a legacy text encoding that cannot print emoji.
    # These two settings make ytmd write UTF-8, which is also what we read here.
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    if run.returncode != 0:
        sys.exit(f"ytmd search failed:\n{run.stderr or run.stdout}")
    return json.loads(run.stdout)[:top]


def clock(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def build_prompt(question: str, passages: list[dict]) -> str:
    blocks = [
        f"[C{i}] Video: {p['title']} | Time: {clock(p['start'])}\n{p['text']}"
        for i, p in enumerate(passages, start=1)
    ]
    return "Passages:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


def ask_gemini(prompt: str, api_key: str) -> str:
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0},
    }
    request = urllib.request.Request(
        API_URL.format(model=MODEL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    # 429 (rate limit) and 503 (overloaded) are temporary, so wait and retry a few times.
    for wait in (2, 5, 15, None):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as err:
            if err.code in (429, 503) and wait is not None:
                print(f"Gemini is busy ({err.code}); retrying in {wait}s...")
                time.sleep(wait)
                continue
            sys.exit(f"Gemini API error {err.code}:\n{err.read().decode('utf-8', 'replace')}")
        except urllib.error.URLError as err:
            sys.exit(f"Could not reach the Gemini API: {err.reason}")
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts).strip()
    except (KeyError, IndexError):
        sys.exit(f"Gemini returned no answer:\n{json.dumps(data, indent=2)[:1500]}")


def check_citations(answer: str, count: int) -> tuple[str, list[int]]:
    """The model only writes markers like [C2]. This code decides what they point to.

    Markers that point at a passage we never sent are removed, so a made-up
    citation can never turn into a link.
    """
    cited: list[int] = []

    def keep_valid(match: re.Match) -> str:
        valid = [int(n) for n in re.findall(r"\d+", match.group(0)) if 1 <= int(n) <= count]
        cited.extend(n for n in valid if n not in cited)
        return "[" + ", ".join(f"C{n}" for n in valid) + "]" if valid else ""

    cleaned = re.sub(r"\[C\d+(?:\s*,\s*C?\d+)*\]", keep_valid, answer)
    return re.sub(r"\s+([.,;])", r"\1", cleaned).strip(), cited


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask a question about saved videos.")
    parser.add_argument("question")
    parser.add_argument("--video", help="limit to one video ID")
    parser.add_argument("--top", type=int, default=5, help="passages to send (default 5)")
    parser.add_argument("--show-passages", action="store_true", help="print what was retrieved")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Set the key first:  set GEMINI_API_KEY=your-key-here")
    if not YTMD.exists():
        sys.exit(f"Put ask.py in the same folder as the ytmd script (looked for {YTMD}).")

    words = keywords(args.question)
    if not words:
        sys.exit("No searchable words in that question. Try naming the topic.")
    passages = search(words, args.top, args.video)
    print(f"Keywords searched: {' '.join(words)}")

    # No evidence -> no model call. Otherwise the model would answer from its own memory.
    if not passages:
        print("\nNothing in the saved videos matches. Not asking the model.")
        return

    if args.show_passages:
        for i, p in enumerate(passages, start=1):
            print(f"\n[C{i}] {p['title']} @ {clock(p['start'])}\n{p['text']}")

    raw = ask_gemini(build_prompt(args.question, passages), api_key)
    if raw.strip().strip(".") == NOT_FOUND:
        print("\nThe saved videos do not answer this. Closest passages, in case they help:")
        for p in passages[:3]:
            print(f"  {p['title']} @ {clock(p['start'])}  {p['url']}")
        return

    answer, cited = check_citations(raw, len(passages))
    print(f"\n{answer}\n")
    if not cited:
        print("WARNING: this answer cites no passage, so it is unverified. Do not rely on it.")
        return
    print("Sources:")
    for n in cited:
        p = passages[n - 1]
        print(f"  [C{n}] {p['title']} @ {clock(p['start'])}  {p['url']}")


if __name__ == "__main__":
    main()
