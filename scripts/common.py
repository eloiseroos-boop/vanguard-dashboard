"""Shared helpers for the funding-dashboard scripts."""
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
CONFIG = ROOT / "config"

DATA_JSON = SITE / "data.json"
TRACKING_JSON = SITE / "tracking.json"
NOTIFIED_JSON = DATA / "notified.json"


def load_config():
    import yaml
    with open(CONFIG / "keywords.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_id(source, key):
    """Stable short id for an opportunity, keyed by source + a natural key."""
    return hashlib.sha1(f"{source}|{key}".encode("utf-8")).hexdigest()[:16]


def today_iso():
    return date.today().isoformat()


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def clean_text(s, limit=420):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(s))
    s = re.sub(r"&[a-z]+;", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0].rstrip(",;.") + "…"
    return s


# --- Date parsing ------------------------------------------------------------

_FRENCH_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
_FR_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(_FRENCH_MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE
)


def parse_iso_date(s):
    """Parse an ISO-ish datetime/date string to a date, or None."""
    if not s:
        return None
    try:
        from dateutil import parser as dtp
        return dtp.parse(str(s)).date()
    except Exception:
        return None


def french_dates(text):
    """Return all French-formatted dates ('7 avril 2026') found in text as date objects."""
    out = []
    for d, mon, y in _FR_DATE_RE.findall(text or ""):
        m = _FRENCH_MONTHS.get(mon.lower())
        if m:
            try:
                out.append(date(int(y), m, int(d)))
            except ValueError:
                pass
    return out


def first_future_iso(iso_list):
    """From a list of ISO datetimes, return the earliest date >= today (ISO string).
    If none are in the future, return the latest one (so 'expired' can be detected)."""
    today = date.today()
    parsed = [d for d in (parse_iso_date(x) for x in (iso_list or [])) if d]
    if not parsed:
        return None
    future = sorted(d for d in parsed if d >= today)
    chosen = future[0] if future else max(parsed)
    return chosen.isoformat()
