"""python -m cloud.engine            one run (what the hourly workflow does)
python -m cloud.engine --no-videos   prices, ratings and cards only
python -m cloud.engine --mail daily  also send the daily (or weekly) email now, to everyone who wants it"""
import argparse
import sys

from . import odds
from .run import run, settings_from_env
from .store import FirestoreStore


def main():
    ap = argparse.ArgumentParser(description="The shared Econova engine.")
    ap.add_argument("--no-videos", action="store_true", help="do not read new videos this run")
    ap.add_argument("--mail", choices=["daily", "weekly"], help="send this email now")
    args = ap.parse_args()
    status = run(FirestoreStore(), settings_from_env(), read_videos=not args.no_videos, force_mail=args.mail, odds_reader=odds.read)
    sys.exit(0 if status["ok"] else 1)


if __name__ == "__main__":
    main()
