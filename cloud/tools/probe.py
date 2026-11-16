"""Can a free cloud runner read what the engine needs? Run by .github/workflows/probe.yml; prints one line per check.
No keys needed. It lists a channel's uploads, reads captions for a few videos and fetches prices."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "app"))
import digest  # noqa: E402
import prices  # noqa: E402


def check(name, fn):
    try:
        print(f"OK   {name}: {fn()}", flush=True)
        return True
    except Exception as err:   # a probe: every failure is a finding
        print(f"FAIL {name}: {type(err).__name__}: {str(err)[:300]}", flush=True)
        traceback.print_exc(limit=1)
        return False


def main():
    state = {"channel_ids": {}}
    found = {}
    for handle in ("@CNBCtelevision", "@markets", "@YahooFinance"):
        def uploads(h=handle):
            cid = digest.channel_id(h, state)
            try:
                ups, how = digest.feed_uploads(cid), "feed"
            except Exception as err:
                print(f"     feed failed for {h}: {type(err).__name__}: {str(err)[:120]}", flush=True)
                ups, how = digest.ytdlp_uploads(cid, count=5), "yt-dlp"
            found[h] = [u for u in ups if not u.get("short")][:2]
            return f"{len(ups)} uploads via {how}; newest: {ups[0]['title'][:60]!r}"
        check(f"uploads {handle}", uploads)
    good = 0
    for handle, videos in found.items():
        for v in videos:
            def captions(v=v):
                text = digest.transcript(v)
                return f"{len(text)} characters, {v.get('duration')}s, captions={v.get('captions')}"
            good += check(f"captions {handle} {v['id']}", captions)
    for symbol in ("NVDA", "^GSPC", "RELIANCE.NS"):
        check(f"price yahoo {symbol}", lambda s=symbol: f"{len(prices.from_yahoo(s)['closes'])} closes")
        check(f"price stooq {symbol}", lambda s=symbol: f"{len(prices.from_stooq(s)['closes'])} closes")
    print(f"\ncaptions read: {good} of {sum(len(v) for v in found.values())}")


if __name__ == "__main__":
    main()
