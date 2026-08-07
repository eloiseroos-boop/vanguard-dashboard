# Vanguard Humanity — Funding Dashboard

An automated dashboard that aggregates open funding opportunities relevant to an
MHPSS programme in Lebanon, refreshes daily with no manual intervention, and
emails you about new matches and approaching deadlines.

- **Static site** on GitHub Pages (no server, free).
- **Daily GitHub Actions workflow** fetches sources, filters for relevance,
  updates `site/data.json`, redeploys, and sends an email digest.
- **Manual-entry form** in the dashboard for login-gated sources.

---

## What it monitors

| Source | How | Status |
|---|---|---|
| **ReliefWeb** | Public API v2 (full-text funding-call query, Lebanon + region) | Automated — **needs a free `appname`** (see below) |
| **EU Funding & Tenders** | Public SEDIA search API (open/forthcoming grants) | Automated |
| **Fondation de France** | Scrape of the public "Appels à projets" listing (page 1) | Automated |
| **OCHA GMS / Lebanon Humanitarian Fund** | Login + eligibility gated | **Manual entry** (use the *+ Add* button) |
| **DevelopmentAid** | Subscription/login gated | **Manual entry** |
| **Expertise France POPS** | JavaScript app, no stable public feed | **Manual entry** |

### Honest limitations
- ReliefWeb has no dedicated "funding calls" feed; we match funding-call phrasing
  in reports, so coverage is keyword-based, not exhaustive.
- EU calls are tagged **"stretch / likely not yet eligible"** — most need 2+ years
  of audited accounts and often a consortium. They're shown, not hidden, by design.
- Fondation de France calls are mostly France-focused; they're tagged so you can
  judge international eligibility. We only read page 1 (robots.txt disallows the
  paginated pages and RSS feed).

---

## First-time setup (≈30 minutes)

### 1. Create a GitHub account
Go to <https://github.com> → **Sign up**. A free account is all you need.

### 2. Create the repository
- Click **+** (top right) → **New repository**.
- Name it e.g. `funding-dashboard`. **Set it to Public** (GitHub Pages is free for
  public repos; note that means your manual notes in `tracking.json` are public —
  fine for funding tracking, but don't put anything sensitive there).
- Do **not** add a README (this project already has one). Click **Create**.

### 3. Upload this project
Easiest (no command line): on the new empty repo page, click
**uploading an existing file**, then drag in **all files and folders** from the
`funding-dashboard/` folder. Commit.

Or with git:
```bash
cd funding-dashboard
git init && git add . && git commit -m "Initial funding dashboard"
git branch -M main
git remote add origin https://github.com/<your-username>/funding-dashboard.git
git push -u origin main
```

### 4. Turn on GitHub Pages
Repo → **Settings** → **Pages** → under **Build and deployment**, set
**Source = GitHub Actions**. (No branch to pick — the workflow deploys it.)

### 5. Add your secrets
Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
Add these (names must match exactly):

| Secret | Value |
|---|---|
| `GMAIL_USER` | the Gmail/Workspace address that will *send* alerts |
| `GMAIL_APP_PASSWORD` | a Google **App Password** (see step 6) — not your login password |
| `ALERT_TO` | `eloise.roos@vanguardhumanity.org` |
| `RELIEFWEB_APPNAME` | add once ReliefWeb approves your appname (step 7) |

### 6. Create the Gmail App Password
1. The sending account needs **2-Step Verification ON**
   (<https://myaccount.google.com/security>).
2. Go to <https://myaccount.google.com/apppasswords>, create one named
   "funding dashboard", copy the 16-character password, and paste it as the
   `GMAIL_APP_PASSWORD` secret.
   *(If your Workspace admin has disabled App Passwords, tell me and we'll switch
   to Resend — a ~10-minute change.)*

### 7. ReliefWeb appname
You already submitted the request form. When the approval email arrives, add the
approved appname as the `RELIEFWEB_APPNAME` secret. Until then, ReliefWeb simply
shows as "skipped" and everything else runs.

### 8. Run it once
Repo → **Actions** tab → enable workflows if prompted → open
**"Update funding dashboard"** → **Run workflow**. After it finishes (green
check), your dashboard is live at:
```
https://<your-username>.github.io/funding-dashboard/
```
It then re-runs automatically every day.

---

## Editing statuses & saving across devices (optional)

Status changes and manual entries save instantly in your browser. To make them
persist across devices and feed the email deadline alerts, connect the dashboard
to the repo:

1. Create a **fine-grained personal access token**:
   <https://github.com/settings/tokens?type=beta> → **Generate new token** →
   **Repository access:** only `funding-dashboard` → **Permissions:** *Contents →
   Read and write* → generate, copy.
2. In the dashboard, click **⚙︎ Sync**, confirm owner/repo, paste the token,
   **Save**. (The token is stored only in your browser.)

Prefer not to store a token? You can also edit `site/tracking.json` directly
through GitHub's web editor.

---

## Tuning what shows up

Everything is controlled by [`config/keywords.yml`](config/keywords.yml):
- add/remove **theme** and **geography** keywords (bilingual EN/FR),
- adjust the **scoring** and the **email alert threshold**,
- change `deadline_highlight_days`, `drop_expired_over_days`, etc.

Commit a change and the next run picks it up.

### Change the refresh frequency
Edit the `cron` line in
[`.github/workflows/update.yml`](.github/workflows/update.yml). Examples:
- Twice daily: `- cron: "20 6,18 * * *"`
- Weekly (Mondays): `- cron: "20 6 * * 1"`

---

## Run locally (for testing / development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/run_all.py         # fetch + build site/data.json
DRY_RUN=1 python scripts/notify.py  # print the email digest without sending

# preview the dashboard
cd site && python3 -m http.server 8000    # then open http://localhost:8000
```

Individual fetchers can be run directly, e.g. `python scripts/fetch_eu.py`.

---

## How the data flows

```
fetch_reliefweb ─┐
fetch_eu ────────┤→ relevance.tag_and_filter → merge (first-seen / new / expired)
fetch_fondation ─┘                                    │
                                                      ▼
                                              site/data.json  ──►  dashboard (site/)
                                                      │
                       notify.py ◄── site/tracking.json (your statuses + manual)
                            │
                            ▼  email digest (new matches + deadlines ≤7d)
```

- `site/data.json` — auto-fetched opportunities (regenerated each run).
- `site/tracking.json` — your statuses/notes + manually added opportunities.
- `data/notified.json` — remembers what was already emailed (no repeats).
