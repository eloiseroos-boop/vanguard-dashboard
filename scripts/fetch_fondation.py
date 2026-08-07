"""Scrape open 'appels à projets' from Fondation de France.

The listing page is static server-rendered HTML. Each card carries the title,
the open date ('Date d'ouverture') and the submission deadline
('Date de dépôt' / 'Date de clôture') plus a teaser — so a single request to
page 1 is enough. We deliberately do NOT fetch the paginated `?start=` pages or
the RSS feed: robots.txt disallows both. Relevance filtering (bilingual FR/EN
keywords) decides what is actually surfaced.
"""
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from common import clean_text, french_dates, make_id

BASE = "https://www.fondationdefrance.org"
LIST_URL = BASE + "/fr/appels-a-projets"
UA = {"User-Agent": "VanguardHumanityFundingBot/1.0 (+eloise.roos@vanguardhumanity.org)"}

_SLUG_RE = re.compile(r"^/fr/appels-a-projets/[a-z0-9-]+$")
_DEADLINE_LABEL = re.compile(
    r"date de d[ée]p[oô]t[^0-9]{0,40}|date de cl[oô]ture[^0-9]{0,40}|date limite[^0-9]{0,40}",
    re.IGNORECASE,
)
_OPEN_LABEL = re.compile(r"date d['’]ouverture\s*:?\s*\d{1,2}\s+\S+\s+\d{4}", re.IGNORECASE)
_DEP_SENT = re.compile(
    r"date de (?:d[ée]p[oô]t|cl[oô]ture)[^0-9]{0,40}\d{1,2}\s+\S+\s+\d{4}(?:\s*à\s*\d{1,2}\s*h\s*\d*)?",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"(\d[\d\s.]{2,}\d)\s*(?:€|euros)", re.IGNORECASE)


def _extract_deadline(text):
    """Return (iso_date, is_approx). Prefer a date following a deadline label."""
    m = _DEADLINE_LABEL.search(text)
    if m:
        ds = french_dates(text[m.end():m.end() + 30])
        if ds:
            return ds[0].isoformat(), False
    ds = french_dates(text)
    future = sorted(d for d in ds if d >= date.today())
    if future:
        return future[0].isoformat(), True
    if ds:
        return max(ds).isoformat(), True
    return None, False


def parse_listing(html):
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0]
        if not _SLUG_RE.match(href) or href in seen:
            continue
        seen.add(href)

        h = a.find_parent(["h1", "h2", "h3", "h4"])
        title = clean_text(a.get_text(" ", strip=True)
                           or (h.get_text(" ", strip=True) if h else ""), 200)
        box = (h.find_parent("div") if h else None) or a.find_parent(["article", "li", "div"])
        boxtext = clean_text(box.get_text(" ", strip=True), 1400) if box else title

        deadline, approx = _extract_deadline(boxtext)

        money = _MONEY_RE.search(boxtext)
        funding = None
        if money:
            funding = "jusqu'à " + re.sub(r"\s+", " ", money.group(1)).strip() + " €"

        desc = boxtext
        if title and desc.startswith(title):
            desc = desc[len(title):]
        desc = _OPEN_LABEL.sub(" ", desc)
        desc = _DEP_SENT.sub(" ", desc)
        desc = re.sub(r"\*+\s*attention[^*]*\*+", " ", desc, flags=re.IGNORECASE)
        desc = clean_text(desc, 360)

        items.append({
            "id": make_id("Fondation de France", href),
            "source": "Fondation de France",
            "source_type": "auto",
            "title": title,
            "donor": "Fondation de France",
            "description": desc,
            "url": BASE + href,
            "funding_range": funding,
            "deadline": deadline,
            "deadline_approx": approx,
            "source_geography": ["France"],
            "eligibility_notes": "",
        })
    return items


def fetch():
    try:
        r = requests.get(LIST_URL, headers=UA, timeout=30)
        r.raise_for_status()
    except Exception as e:
        return [], f"error: {str(e)[:160]}"
    items = parse_listing(r.text)
    return items, "" if items else "warning: no cards parsed (page structure may have changed)"


if __name__ == "__main__":
    import json
    opps, note = fetch()
    print(f"[fondation] {len(opps)} cards. note={note!r}")
    print(json.dumps(opps[:4], ensure_ascii=False, indent=2))
