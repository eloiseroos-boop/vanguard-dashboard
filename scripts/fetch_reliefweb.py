"""Fetch funding-relevant items from the ReliefWeb API v2.

Important context:
  * ReliefWeb has no dedicated "funding calls" content type. Funding
    opportunities appear as *reports* (e.g. "Call for Proposals", "Request for
    Applications", appeals) so we do a full-text query for those phrases,
    filtered to Lebanon + the surrounding region.
  * Since 1 Nov 2025 the API requires a PRE-APPROVED appname. Set it via the
    RELIEFWEB_APPNAME environment variable (a GitHub Actions secret). Until the
    appname is approved this fetcher skips cleanly so the rest of the pipeline
    still runs.

Deadlines are rarely structured on ReliefWeb, so we best-effort parse them from
the body text and flag them approximate.
"""
import os
import re
from datetime import date

import requests

from common import clean_text, make_id, parse_iso_date

API = "https://api.reliefweb.int/v2/reports"

COUNTRIES = ["Lebanon", "Syrian Arab Republic", "Jordan", "Iraq",
             "occupied Palestinian territory", "World"]

# Full-text query aimed at funding calls rather than situation reports.
QUERY_VALUE = ('"call for proposals" OR "request for applications" OR '
               '"request for proposals" OR "call for applications" OR '
               '"funding opportunity" OR "grant opportunity" OR '
               '"expression of interest" OR "notice of funding"')

_DEADLINE_RE = re.compile(
    r"(?:deadline|closing date|submission deadline|apply by|applications? (?:close|due))"
    r"[^0-9]{0,25}(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)


def _extract_deadline(text):
    m = _DEADLINE_RE.search(text or "")
    if not m:
        return None, False
    d = parse_iso_date(m.group(1))
    return (d.isoformat(), True) if d else (None, False)


def _norm(report):
    f = report.get("fields", {}) or {}
    title = clean_text(f.get("title"), 220)
    if not title:
        return None
    url = f.get("url_alias") or f.get("url") or ""
    body = f.get("body") or ""
    deadline, approx = _extract_deadline(body)
    source_names = [s.get("name") for s in (f.get("source") or []) if s.get("name")]
    countries = [c.get("name") for c in (f.get("country") or []) if c.get("name")]
    return {
        "id": make_id("ReliefWeb", url or title),
        "source": "ReliefWeb",
        "source_type": "auto",
        "title": title,
        "donor": ", ".join(source_names) or "ReliefWeb source",
        "description": clean_text(body, 360),
        "url": url,
        "funding_range": None,
        "deadline": deadline,
        "deadline_approx": approx,
        "source_geography": countries,
        "eligibility_notes": "",
    }


def fetch():
    appname = os.environ.get("RELIEFWEB_APPNAME", "").strip()
    if not appname:
        return [], ("skipped: RELIEFWEB_APPNAME not set — submit the appname form and "
                    "add it as a GitHub secret to activate this source")

    params = {
        "appname": appname,
        "query[value]": QUERY_VALUE,
        "query[operator]": "AND",
        "filter[field]": "country.name",
        "filter[value][]": COUNTRIES,
        "filter[operator]": "OR",
        "limit": 40,
        "sort[]": "date.created:desc",
        "fields[include][]": ["title", "url_alias", "url", "body",
                              "source.name", "country.name", "date.created", "format.name"],
    }
    try:
        r = requests.get(API, params=params, timeout=40)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [], f"error: {str(e)[:160]}"

    opps = []
    for rep in data.get("data", []) or []:
        o = _norm(rep)
        if o:
            opps.append(o)
    return opps, "" if opps else "ok: no matching funding calls right now"


if __name__ == "__main__":
    import json
    opps, note = fetch()
    print(f"[reliefweb] {len(opps)} items. note={note!r}")
    print(json.dumps(opps[:2], ensure_ascii=False, indent=2))
