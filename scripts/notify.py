"""Email digest: new matches + tracked opportunities with deadlines approaching.

Sends ONE digest with up to two sections:
  1. New opportunities found this run that clear the alert score threshold.
  2. Tracked/saved opportunities (a status you've set, or a manual entry) whose
     deadline falls within `deadline_alert_days`.

Sending uses Gmail SMTP with an app password. Configure via env / GitHub secrets:
  GMAIL_USER            the Gmail/Workspace address that sends
  GMAIL_APP_PASSWORD    a Google app password (NOT your normal password)
  ALERT_TO              recipient (default: eloise.roos@vanguardhumanity.org)
  ALERT_FROM            optional From (default: GMAIL_USER)

If credentials are missing, or DRY_RUN=1, it prints the digest and sends nothing
(and does not record anything as notified, so it stays testable).
"""
import os
import smtplib
import sys
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from common import (DATA_JSON, NOTIFIED_JSON, TRACKING_JSON, load_config,
                    load_json, save_json)

ACTIVE_STATUSES = {"New", "Reviewing", "Applied"}
DEFAULT_TO = "eloise.roos@vanguardhumanity.org"


def _deadline_str(o):
    d = o.get("deadline")
    if not d:
        return "no deadline stated"
    return d + (" (approx.)" if o.get("deadline_approx") else "")


def _collect(config):
    data = load_json(DATA_JSON, {"opportunities": []})
    tracking = load_json(TRACKING_JSON, {})
    notified = load_json(NOTIFIED_JSON, {"new": [], "deadline": []})

    statuses = {k: v for k, v in tracking.items() if not k.startswith("_")}
    manual = tracking.get("_manual", []) or []
    auto = data.get("opportunities", [])
    everything = auto + manual

    threshold = config.get("alert_score_threshold", 30)
    window_days = config.get("deadline_alert_days", 7)
    horizon = (date.today() + timedelta(days=window_days)).isoformat()
    today = date.today().isoformat()

    new_matches = [
        o for o in auto
        if o.get("is_new") and not o.get("expired")
        and o.get("relevance_score", 0) >= threshold
        and o["id"] not in notified["new"]
    ]

    deadline_matches = []
    for o in everything:
        dl = o.get("deadline")
        if not dl or dl < today or dl > horizon:
            continue
        if o["id"] in notified["deadline"]:
            continue
        tracked = (o.get("source_type") == "manual"
                   or statuses.get(o["id"], {}).get("status") in ACTIVE_STATUSES)
        if tracked:
            deadline_matches.append(o)

    return new_matches, deadline_matches, notified, window_days


def _render(new_matches, deadline_matches, window_days):
    def card_txt(o):
        return (f"- {o['title']}\n"
                f"    Source: {o['source']} | Deadline: {_deadline_str(o)} | "
                f"Score: {o.get('relevance_score','-')}\n"
                f"    {(o.get('eligibility_notes') or '').strip()}\n"
                f"    {o.get('url','')}\n")

    def card_html(o):
        elig = escape(o.get("eligibility_notes") or "")
        return (
            f'<tr><td style="padding:12px 0;border-bottom:1px solid #eee;">'
            f'<a href="{escape(o.get("url",""))}" style="font-weight:600;color:#1a56db;'
            f'text-decoration:none;font-size:15px;">{escape(o["title"])}</a><br>'
            f'<span style="color:#555;font-size:13px;">{escape(o["source"])} '
            f'&nbsp;·&nbsp; Deadline: <b>{escape(_deadline_str(o))}</b> '
            f'&nbsp;·&nbsp; Relevance {o.get("relevance_score","-")}</span>'
            + (f'<br><span style="color:#9a6700;font-size:12px;">{elig}</span>' if elig else "")
            + "</td></tr>")

    lines = ["Vanguard Humanity — funding dashboard alert", "=" * 44, ""]
    if new_matches:
        lines.append(f"NEW MATCHES ({len(new_matches)})\n")
        lines += [card_txt(o) for o in new_matches]
    if deadline_matches:
        lines.append(f"\nTRACKED — DEADLINE WITHIN {window_days} DAYS ({len(deadline_matches)})\n")
        lines += [card_txt(o) for o in deadline_matches]
    text = "\n".join(lines)

    def section_html(title, items):
        if not items:
            return ""
        rows = "".join(card_html(o) for o in items)
        return (f'<h2 style="font-size:16px;color:#111;margin:22px 0 4px;">{title}</h2>'
                f'<table style="width:100%;border-collapse:collapse;">{rows}</table>')

    html = (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;'
        'max-width:640px;margin:0 auto;color:#222;">'
        '<h1 style="font-size:18px;margin:0 0 2px;">Vanguard Humanity — funding alert</h1>'
        f'<div style="color:#777;font-size:12px;">{escape(date.today().isoformat())}</div>'
        + section_html(f"New matches ({len(new_matches)})", new_matches)
        + section_html(f"Tracked — deadline within {window_days} days ({len(deadline_matches)})",
                       deadline_matches)
        + '<p style="color:#999;font-size:11px;margin-top:24px;">'
        'Automated by your funding dashboard. Update statuses in the dashboard.</p></div>'
    )
    return text, html


def main():
    config = load_config()
    new_matches, deadline_matches, notified, window_days = _collect(config)

    if not new_matches and not deadline_matches:
        print("[notify] nothing to alert.")
        return

    text, html = _render(new_matches, deadline_matches, window_days)

    user = os.environ.get("GMAIL_USER", "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    to_addr = os.environ.get("ALERT_TO", DEFAULT_TO).strip()
    from_addr = os.environ.get("ALERT_FROM", user).strip() or user
    dry = os.environ.get("DRY_RUN") == "1" or not (user and pw)

    subject = "Funding alert: "
    bits = []
    if new_matches:
        bits.append(f"{len(new_matches)} new")
    if deadline_matches:
        bits.append(f"{len(deadline_matches)} closing soon")
    subject += ", ".join(bits)

    if dry:
        print("[notify] DRY RUN — no email sent (missing creds or DRY_RUN=1).")
        print("Subject:", subject)
        print(text)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.sendmail(from_addr, [to_addr], msg.as_string())
        print(f"[notify] sent to {to_addr}: {subject}")
    except Exception as e:
        print(f"[notify] ERROR sending email: {e}", file=sys.stderr)
        sys.exit(1)

    # Record what we alerted so we don't repeat it next run.
    notified["new"] = sorted(set(notified["new"]) | {o["id"] for o in new_matches})
    notified["deadline"] = sorted(set(notified["deadline"]) | {o["id"] for o in deadline_matches})
    save_json(NOTIFIED_JSON, notified)


if __name__ == "__main__":
    main()
