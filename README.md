# ⚡ Job Scanner

Finds **freshly posted remote jobs** (Azure, cloud, AVD, data/SQL, security, support)
matching ~220 job titles, and heavily prioritizes **weekend / after-hours / night-shift**
roles. Runs entirely on GitHub — no server to maintain:

- **GitHub Actions** runs `scan.py` on a schedule (every ~10–30 min), scores and
  dedupes jobs, and commits the results to `docs/data/jobs.json`.
- **GitHub Pages** serves the static dashboard in `docs/` at a public URL you can
  open from any phone, tablet, or laptop. It's installable as a PWA.

The dashboard shows jobs posted in the last **4 hours** by default (configurable up
to 24h), with HOT / WEEKEND / AFTER-HOURS / NEWEST sections, filters, match scores
that decay as postings age, and browser notifications for strong matches.

## Live dashboard

**https://mjjaber.github.io/job-scanner/**

## How it works

```
GitHub Actions (cron)          GitHub Pages (static)
┌───────────────────┐          ┌──────────────────────┐
│ scan.py           │  commit  │ docs/index.html      │
│  ├ sources.py     │ ───────► │  reads               │
│  ├ scoring.py     │          │ docs/data/jobs.json  │
│  └ job_titles.txt │          └──────────────────────┘
└───────────────────┘
```

Sources are keyless public endpoints with real posting timestamps: RemoteOK API,
Remotive API, Jobicy API, WeWorkRemotely RSS, plus **Greenhouse** and **Lever**
public career-board APIs for the companies listed in `companies.json`.

Scoring = title match against `job_titles.txt` (up to 40) + keyword relevance
(Azure/AVD/Nerdio/M365/SQL/data/security, up to 25) + remote bonus + weekend /
after-hours bonuses. The browser adds recency points (up to +25 for <30 min old),
so scores decay naturally as jobs age.

**Applied / Favorite / Ignored marks are stored in each browser's localStorage** —
they do not sync between devices (that's the trade-off for having no backend).

## Manual "Scan now" from the dashboard

The **⚡ Scan** button triggers a real scan on GitHub (instead of waiting for the
next scheduled run). Because the dashboard is a public static page, GitHub needs
proof it's you: a **fine-grained personal access token**, pasted once per device
and stored only in that browser's localStorage — never in the repo.

Create it at **github.com/settings/personal-access-tokens → Generate new token**:

- *Only select repositories* → `job-scanner`
- *Repository permissions* → **Actions: Read and write** (nothing else)

Then click ⚡ Scan and paste it when prompted. Results appear automatically when
the scan finishes (~1–2 min). Without a token, the button opens the repo's
Actions page where *Run workflow* does the same thing with one click.

## Configuration

Everything lives in two JSON files — no code changes needed:

- **`config.json`** — max age, min score, remote-only, weekend/after-hours score
  bonuses, notification threshold, and per-source enable/interval settings.
- **`companies.json`** — Greenhouse and Lever board names to poll
  (from `boards.greenhouse.io/<name>` / `jobs.lever.co/<name>`). Invalid names
  are logged and skipped, so it's safe to experiment.
- **`job_titles.txt`** — one title per line; numbering, headers, and blank lines
  are ignored. Replace the file wholesale whenever you like.

Commit + push a change to any of these and the next scheduled scan uses it.

## Setup (one time)

```bash
git clone https://github.com/mjjaber/job-scanner.git
```

If forking/recreating: Settings → Pages → Source: **Deploy from a branch**,
branch `main`, folder `/docs`. Actions are enabled by default.

## Run locally

```bash
pip install -r requirements.txt
python scan.py                      # one scan cycle, writes docs/data/jobs.json
python -m http.server -d docs 8080  # then open http://localhost:8080
```

(Opening `docs/index.html` directly as a file won't work — browsers block
`fetch()` from `file://` pages, so serve it with any static server.)

## Update / deploy

Edit → commit → push. That's the whole deployment:

```bash
git add -A
git commit -m "tune scoring"
git push
```

The dashboard updates when Pages redeploys (~1 min); scans pick up config
changes on their next run.

## Troubleshooting

- **Dashboard shows old data / "last scan Xh ago"** — check the *Actions* tab for
  failed or delayed runs. GitHub pauses cron workflows after **60 days without a
  commit**; push anything (or press *Run workflow*) to revive it.
- **A source shows ⚠ in the footer** — that source errored last scan; the others
  still ran. Details are in the Actions run log. 404 on a Greenhouse/Lever board
  means the company changed ATS — remove or replace it in `companies.json`.
- **No notifications** — click 🔔 and allow notifications; they only fire while a
  tab (or installed PWA) is open, for jobs above the threshold or weekend/after-
  hours matches. iOS requires the PWA to be installed to home screen.
- **Too much noise / too quiet** — raise/lower `min_score` in `config.json`
  (storage filter) or use the dashboard's *Min score* filter (view filter).

## Roadmap

- Phase 2: more sources (more ATS boards, Built In, Working Nomads), richer
  notification targets (Telegram/Discord via a tiny Actions step).
- Phase 3: smarter ranking, ATS detection, application tracking.
