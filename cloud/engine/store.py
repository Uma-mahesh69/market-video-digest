"""Where the engine keeps things: Firestore in production, a dict in tests. Same five methods on both.

Collections: stocks (one card a ticker), charts (a year of closes), market (overview, analysts, calendar, videos, meta,
status), videos (Gemini's notes, written once), users (owned by each user; read here for their stocks and email
choices), requests (tickers users asked for), mail (what was sent to whom), engine (the engine's own state)."""
import json
import os


class MemoryStore:
    def __init__(self, data=None):
        self.data = data or {}
        self.writes = 0

    def get(self, col, key):
        doc = self.data.get(col, {}).get(key)
        return json.loads(json.dumps(doc)) if doc is not None else None

    def set(self, col, key, doc, merge=False):
        check(doc)
        docs = self.data.setdefault(col, {})
        docs[key] = {**((docs.get(key) or {}) if merge else {}), **json.loads(json.dumps(doc))}
        self.writes += 1

    def delete(self, col, key):
        self.data.get(col, {}).pop(key, None)

    def all(self, col):
        return {k: json.loads(json.dumps(v)) for k, v in self.data.get(col, {}).items()}

    def since(self, col, field, value):
        return {k: v for k, v in self.all(col).items() if str(v.get(field) or "") >= value}


def check(doc, inside_list=False):
    """Firestore refuses a list directly inside a list; say so here, where the mistake is made."""
    if isinstance(doc, dict):
        for v in doc.values():
            check(v)
    elif isinstance(doc, list):
        if inside_list:
            raise ValueError("Firestore cannot store a list inside a list")
        for v in doc:
            check(v, inside_list=True)


class FirestoreStore:
    """Firestore with the project's service account, which the security rules do not bind. Credentials:
    FIREBASE_SERVICE_ACCOUNT (the key file's JSON, a GitHub secret), or GOOGLE_APPLICATION_CREDENTIALS, or the local
    emulator (FIRESTORE_EMULATOR_HOST with GCLOUD_PROJECT)."""

    def __init__(self):
        from google.cloud import firestore
        raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "").strip()
        if os.environ.get("FIRESTORE_EMULATOR_HOST"):   # the local emulator takes anyone
            from google.auth.credentials import AnonymousCredentials
            self.db = firestore.Client(project=os.environ.get("GCLOUD_PROJECT", "demo-md"), credentials=AnonymousCredentials())
        elif raw:
            from google.oauth2 import service_account
            info = json.loads(raw)
            self.db = firestore.Client(project=info["project_id"], credentials=service_account.Credentials.from_service_account_info(info))
        else:
            self.db = firestore.Client()
        self.writes = 0

    def get(self, col, key):
        snap = self.db.collection(col).document(key).get()
        return snap.to_dict() if snap.exists else None

    def set(self, col, key, doc, merge=False):
        check(doc)
        self.db.collection(col).document(key).set(doc, merge=merge)
        self.writes += 1

    def delete(self, col, key):
        self.db.collection(col).document(key).delete()

    def all(self, col):
        return {d.id: d.to_dict() for d in self.db.collection(col).stream()}

    def since(self, col, field, value):
        from google.cloud.firestore_v1.base_query import FieldFilter
        return {d.id: d.to_dict() for d in self.db.collection(col).where(filter=FieldFilter(field, ">=", value)).stream()}


def doc_id(ticker):
    """A ticker as a document name: Firestore names cannot hold a slash, and ^GSPC reads better as GSPC."""
    return str(ticker).replace("/", "-").replace("^", "_")
