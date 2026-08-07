"""Orchestrator: fetch every source, tag + filter, merge, and write site/data.json.

Run by the scheduled GitHub Actions workflow. Each source is isolated so one
failing source never blocks the others; per-source status is written into the
data file so the dashboard can show (e.g.) "ReliefWeb: awaiting appname".
"""
import sys
from datetime import date, timedelta

import fetch_eu
import fetch_fondation
import fetch_reliefweb
import merge as merge_mod
import relevance
from common import DATA_JSON, load_config, load_json, now_iso, save_json, today_iso

SOURCES = [
    ("ReliefWeb", fetch_reliefweb.fetch),
    ("EU Funding & Tenders", fetch_eu.fetch),
    ("Fondation de France", fetch_fondation.fetch),
]


def _sort_key(o):
    """Open, soonest deadline first; undated next; expired last. Then relevance."""
    dl = o.get("deadline")
    expired = o.get("expired")
    bucket = 2 if expired else (0 if dl else 1)
    return (bucket, dl or "9999-12-31", -o.get("relevance_score", 0))


def main():
    config = load_config()
    previous = load_json(DATA_JSON, {}).get("opportunities", [])

    raw, sources = [], []
    for name, fn in SOURCES:
        try:
            opps, note = fn()
            status = "ok"
            if not opps and note.startswith("skipped"):
                status = "skipped"
            elif note.startswith("error"):
                status = "error"
            elif note.startswith("warning") or note.startswith("partial"):
                status = "warning"
            sources.append({"name": name, "status": status, "message": note,
                            "count": len(opps)})
            raw.extend(opps)
            print(f"[{name}] fetched {len(opps)} raw ({status}) {note}")
        except Exception as e:  # noqa: BLE001 — never let one source kill the run
            sources.append({"name": name, "status": "error",
                            "message": str(e)[:200], "count": 0})
            print(f"[{name}] ERROR: {e}", file=sys.stderr)

    fresh = relevance.tag_and_filter(raw, config)
    fresh_ids = {o["id"] for o in fresh}

    # Re-validate previously-seen items that fell out of this fetch against the
    # CURRENT rules (recomputes tags — no stale carry-over), then keep the ones
    # still open + only recently vanished. This smooths source pagination churn
    # without ever resurrecting items the rules would now reject.
    stale = [dict(p) for p in previous if p["id"] not in fresh_ids]
    stale_revalidated = relevance.tag_and_filter(stale, config)
    carried = merge_mod.carryforward(stale_revalidated,
                                     grace_days=config.get("carry_forward_grace_days", 14))

    combined = merge_mod.stamp(previous, fresh + carried)

    # Drop stale index artifacts: deadlines long past. Keep recently-closed ones.
    cutoff_days = config.get("drop_expired_over_days", 45)
    cutoff = (date.today() - timedelta(days=cutoff_days)).isoformat()
    merged = [o for o in combined if not (o.get("deadline") and o["deadline"] < cutoff)]

    merged.sort(key=_sort_key)

    new_count = sum(1 for o in merged if o.get("is_new"))
    open_count = sum(1 for o in merged if not o.get("expired"))
    by_source = {}
    for o in merged:
        by_source[o["source"]] = by_source.get(o["source"], 0) + 1

    data = {
        "meta": {
            "generated_at": now_iso(),
            "run_date": today_iso(),
            "counts": {"total": len(merged), "open": open_count,
                       "new": new_count, "by_source": by_source},
            "sources": sources,
            "deadline_highlight_days": config.get("deadline_highlight_days", 30),
        },
        "opportunities": merged,
    }
    save_json(DATA_JSON, data)
    print(f"\nWrote {DATA_JSON} — {len(merged)} opportunities "
          f"({new_count} new, {open_count} open).")


if __name__ == "__main__":
    main()
