"""Relevance tagging + filtering.

Takes opportunities from the fetchers (or previously-stored items being
re-validated) and:
  - tags geography + theme buckets from keywords.yml (recomputed from scratch,
    so the function is idempotent and safe to re-run on stored items)
  - drops anything with no theme match, or that is out of scope (unless its
    source is always-kept, or it matches a core humanitarian theme)
  - attaches eligibility flags (so stretch opportunities are tagged, not hidden)
  - computes a relevance score used for sorting + email alert thresholds

Fetchers pass any source-provided geography in `source_geography` (e.g. the
country a ReliefWeb report is tagged with); it is folded into the text that
keyword matching runs against, never trusted as a pre-set bucket.
"""


def _matches(text, keywords):
    return [k for k in keywords if k in text]


def tag_and_filter(opps, config):
    geographies = config["geographies"]
    themes_cfg = config["themes"]
    in_scope = set(config["in_scope_geographies"])
    core_themes = set(config.get("core_themes", []))
    relaxed_sources = set(config.get("always_keep_on_theme_sources", []))
    elig_rules = config.get("eligibility_flags", [])
    scoring = config["scoring"]

    kept = []
    for o in opps:
        haystack = " ".join([
            o.get("title", "") or "",
            o.get("description", "") or "",
            o.get("donor") or "",
            " ".join(o.get("source_geography") or []),
        ]).lower()

        geos = sorted(g for g, kws in geographies.items() if _matches(haystack, kws))
        matched_themes = sorted(t for t, kws in themes_cfg.items() if _matches(haystack, kws))

        # Keep rule: must match a theme, AND be in geographic scope, or from an
        # always-keep source, or match a core humanitarian theme (those calls
        # are often country-less but still relevant).
        if not matched_themes:
            continue
        keep = (any(g in in_scope for g in geos)
                or o.get("source") in relaxed_sources
                or any(t in core_themes for t in matched_themes))
        if not keep:
            continue

        if not geos:  # country-less core-theme call → treat as unrestricted
            geos = ["Unspecified"]

        score = sum(scoring["geography"].get(g, 0) for g in geos)
        score += min(len(matched_themes) * scoring["theme_each"], scoring["theme_max"])
        reasons = [f"geo:{g}" for g in geos] + [f"theme:{t}" for t in matched_themes]

        notes = []
        for rule in elig_rules:
            if o.get("source") in (rule.get("match_sources") or []):
                notes.append(rule["note"])
            elif any(k in haystack for k in (rule.get("match_keywords") or [])):
                notes.append(rule["note"])
        seen, elig = set(), []
        for n in notes:
            if n not in seen:
                seen.add(n)
                elig.append(n)

        o["geography"] = geos
        o["themes"] = matched_themes
        o["relevance_score"] = score
        o["relevance_reasons"] = reasons
        o["eligibility_notes"] = "  •  ".join(elig)
        kept.append(o)

    kept.sort(key=lambda x: x["relevance_score"], reverse=True)
    return kept
