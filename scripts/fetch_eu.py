"""Fetch open/forthcoming EU grant calls from the Funding & Tenders portal.

Uses the portal's public SEDIA search API. The reliable request shape (found by
probing) is multipart/form-data with the `query`, `languages` and `sort` parts
sent as JSON-typed fields. We filter server-side to open + forthcoming grants,
then rely on relevance.py (theme match) to cut the (large, noisy) result set
down to what's actually relevant. The portal's own text ranking is weak, so we
do NOT trust it for relevance — we just use several text queries to widen recall.
"""
import requests

from common import clean_text, first_future_iso, make_id

ENDPOINT = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"

# Open (31094502) + Forthcoming (31094501) grant/tender topics (types 1,2,8).
_GRANT_QUERY = ('{"bool":{"must":['
                '{"terms":{"type":["1","2","8"]}},'
                '{"terms":{"status":["31094501","31094502"]}}]}}')
_SORT = '{"field":"sortStatus","order":"ASC"}'

# Text queries used to widen recall. Relevance filtering happens later.
_TEXT_QUERIES = [
    "humanitarian", "mental health", "psychosocial", "refugee", "protection",
    "Lebanon", "Syria", "civil society", "displacement", "human rights",
]

TOPIC_URL = ("https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
             "screen/opportunities/topic-details/{}")


def _search(text, page=1, size=50):
    files = {
        "query": (None, _GRANT_QUERY, "application/json"),
        "languages": (None, '["en"]', "application/json"),
        "sort": (None, _SORT, "application/json"),
        "pageNumber": (None, str(page)),
        "pageSize": (None, str(size)),
    }
    r = requests.post(ENDPOINT, params={"apiKey": "SEDIA", "text": text},
                      files=files, timeout=45)
    r.raise_for_status()
    return r.json()


def _norm(result):
    m = result.get("metadata", {}) or {}

    def first(key):
        v = m.get(key)
        return v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else None)

    identifier = first("identifier") or first("callIdentifier")
    title = first("title") or clean_text(result.get("summary"), 160)
    if not identifier and not title:
        return None

    deadline = first_future_iso(m.get("deadlineDate"))
    url = result.get("url") or ""
    if "topic-details" not in url and "competitive" not in url and identifier:
        url = TOPIC_URL.format(identifier)

    desc_bits = []
    if identifier:
        desc_bits.append(f"Call/topic: {identifier}.")
    summ = clean_text(result.get("summary"), 300)
    if summ and summ.lower() not in (title or "").lower():
        desc_bits.append(summ)

    return {
        "id": make_id("EU Funding & Tenders", identifier or url),
        "source": "EU Funding & Tenders",
        "source_type": "auto",
        "title": clean_text(title, 200),
        "donor": "European Union",
        "description": " ".join(desc_bits).strip(),
        "url": url,
        "funding_range": None,
        "deadline": deadline,
        "deadline_approx": False,
        "source_geography": [],
        "eligibility_notes": "",
    }


def fetch():
    by_id = {}
    errors = 0
    for text in _TEXT_QUERIES:
        try:
            data = _search(text, page=1, size=50)
        except Exception:
            errors += 1
            continue
        for res in data.get("results", []) or []:
            o = _norm(res)
            if o and o["id"] not in by_id:
                by_id[o["id"]] = o

    opps = list(by_id.values())
    note = ""
    if errors == len(_TEXT_QUERIES):
        note = "error: all EU queries failed"
    elif errors:
        note = f"partial: {errors}/{len(_TEXT_QUERIES)} queries failed"
    return opps, note


if __name__ == "__main__":
    import json
    opps, note = fetch()
    print(f"[eu] {len(opps)} raw opportunities. note={note!r}")
    print(json.dumps(opps[:3], ensure_ascii=False, indent=2))
