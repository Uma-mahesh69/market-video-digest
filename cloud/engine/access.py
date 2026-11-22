"""Who may use the site during the private beta: the members list.

The list is the GitHub secret BETA_MEMBERS (email addresses, separated by commas, spaces or new lines). It is a
secret, not a file, because the repository is public and the addresses are personal. Each run copies it into
Firestore's `members/{email}` documents, which the security rules check on every read and write: an address that is
not there can sign in with Google but sees nothing, and can save nothing. Taking an address off the list takes its
access away on the next run (its own saved list stays, so it can still download or delete it).

When BETA_MEMBERS is not set, nothing is changed: the members already in Firestore stay as they are (they can also be
added by hand in the Firebase console, one document per address, the address as the document's id)."""
import re

EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def parse(text):
    """The addresses in BETA_MEMBERS, lower case, each once, in order. None when the secret is not set at all."""
    if text is None or not str(text).strip():
        return None
    out = []
    for word in re.split(r"[\s,;]+", str(text)):
        word = word.strip().strip("<>").lower()
        if EMAIL.match(word) and word not in out:
            out.append(word)
    return out


def sync(store, text, today, log=print):
    """Make Firestore's members match BETA_MEMBERS. Returns the set of members as they now stand."""
    have = store.all("members") or {}
    wanted = parse(text)
    if wanted is None:
        log(f"Members: BETA_MEMBERS is not set; the {len(have)} member(s) in Firestore stay as they are")
        return set(have)
    if not wanted:
        # a secret with no valid address in it is a typo, not "lock everyone out": change nothing
        log("Members: BETA_MEMBERS has no valid address in it, so the list was not changed")
        return set(have)
    added = [e for e in wanted if e not in have]
    removed = [e for e in have if e not in wanted]
    for e in added:
        store.set("members", e, {"email": e, "added": today.isoformat()})
    for e in removed:
        store.delete("members", e)
    log(f"Members: {len(wanted)} on the list" + (f", {len(added)} added" if added else "") + (f", {len(removed)} removed" if removed else ""))
    return set(wanted)


def only_members(users, members):
    """The accounts whose sign-in address is on the list: the only ones the engine works for or emails."""
    return {uid: u for uid, u in (users or {}).items() if str((u or {}).get("email") or "").lower() in members}
