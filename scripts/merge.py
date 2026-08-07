"""Merge bookkeeping across runs.

Split into two small, single-purpose helpers so the orchestrator can re-validate
carried-forward items against the *current* relevance rules (avoiding stale tags):

  * stamp()        — set date_first_seen / is_new / last_seen / expired
  * carryforward() — of the previously-seen items that fell out of this fetch but
                     STILL pass relevance, keep the ones that are still open and
                     only recently vanished (smooths over source pagination churn)
"""
from datetime import date


def stamp(previous, items):
    run_date = date.today().isoformat()
    prev_by_id = {o["id"]: o for o in previous}
    for o in items:
        prev = prev_by_id.get(o["id"])
        o["date_first_seen"] = prev.get("date_first_seen", run_date) if prev else run_date
        o["is_new"] = prev is None
        o["last_seen"] = run_date
        o["expired"] = bool(o.get("deadline")) and o["deadline"] < run_date
    return items


def carryforward(revalidated_stale, grace_days=14):
    run_date = date.today()
    out = []
    for p in revalidated_stale:
        dl = p.get("deadline")
        last_seen = p.get("last_seen") or p.get("date_first_seen")
        try:
            missing_days = (run_date - date.fromisoformat(last_seen)).days
        except (TypeError, ValueError):
            missing_days = 999
        if dl and dl >= run_date.isoformat() and missing_days <= grace_days:
            out.append(p)
    return out
