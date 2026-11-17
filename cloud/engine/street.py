"""Wall Street's view (TipRanks), inside the key's monthly allowance.

A free TipRanks key gives 50 calls a month, and one call can ask about many stocks. So the engine makes a few calls a
weekday, each for a batch of stocks: the ones users hold first, then whichever was looked up longest ago. Ratings move
slowly, so a stock refreshed every few days is current enough; every card says when its rating was read."""
import re
from datetime import date, timedelta

from . import ROOT  # noqa: F401
import tipranks


def weekdays_left(day):
    """Weekdays from this day to the end of its month, this day included."""
    n, d = 0, day
    while d.month == day.month:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return max(n, 1)


def allowance(usage, state, today, limits):
    """How many calls may still be made today."""
    use = state.setdefault("tipranks", {})
    if use.get("day") != today.isoformat():
        use.update(day=today.isoformat(), today=0)
    if today.weekday() >= 5:
        return 0
    left = (usage or {}).get("remaining")
    if left is None:
        return 0   # TipRanks did not say what is left: do not guess with someone's monthly allowance
    per_day = max(1, (left - limits["tipranks_reserve"]) // weekdays_left(today)) if left > limits["tipranks_reserve"] else 0
    return max(0, min(limits["tipranks_calls_per_day"], per_day) - use["today"])


def order(wanted, first, street):
    """Every stock TipRanks can be asked about (US listings, not indexes), users' stocks first, then the stalest."""
    first = set(first)
    known = [t for t in dict.fromkeys(str(t).upper() for t in wanted if t) if re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", t) and not tipranks.NON_US.search(t)]
    return sorted(known, key=lambda t: (t not in first, (street.get(t) or {}).get("at") or "", t))


def refresh(key, state, street, wanted, first, today, limits, log=print, client=None):
    """Bring some of `street` ({ticker: row}) up to date. Never raises: Wall Street's view is extra."""
    if not key and client is None:
        return street
    try:
        tr = client or tipranks.Client(key)
        tr.start()
        tools = tr.tools()
        tool = next((t for t in tools if t.get("name") == tipranks.TOOL), None)
        if tool is None:
            raise tipranks.TipRanksError(f"TipRanks has no {tipranks.TOOL} tool any more")
        usage = tipranks.usage_now(tr, tools)
        calls = allowance(usage, state, today, limits)
        queue = [t for t in order(wanted, first, street) if (street.get(t) or {}).get("at") != today.isoformat()]
        arg, is_list = tipranks.ticker_argument(tool)
        state["tipranks"].update(limit=(usage or {}).get("limit"), remaining=(usage or {}).get("remaining"))
        done = 0
        while calls > 0 and queue:
            batch, queue = queue[:limits["tipranks_batch"]], queue[limits["tipranks_batch"]:]
            state["tipranks"]["today"] += 1   # counted before the call: a call that fails is still charged
            calls -= 1
            for r in tipranks.rows(tipranks.payload(tr.call(tipranks.TOOL, {arg: batch if is_list else ",".join(batch)}))):
                street[r["ticker"]] = {**r, "at": today.isoformat()}
                done += 1
        log(f"TipRanks: {done} stocks refreshed in {state['tipranks']['today']} call(s) today; {len(queue)} waiting their turn")
    except Exception as err:
        log(f"TipRanks: not refreshed ({type(err).__name__}: {str(err)[:160]})")
    return street
