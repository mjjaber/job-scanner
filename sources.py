"""Job source adapters. Each is a function taking the config dict and returning
a list of raw job dicts: title, company, location, remote, salary, salary_min,
url, description, posted_at (aware datetime, UTC).

All sources are keyless public endpoints with real posting timestamps.
To add a source: write a fetch function and register it in SOURCES at the bottom.
"""
import email.utils
import html as _html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0.0.0 Safari/537.36")}

_TAG_RX = re.compile(r"<[^>]+>")


def strip_html(s):
    s = _html.unescape(s or "")
    return re.sub(r"\s+", " ", _TAG_RX.sub(" ", s)).strip()


def get(url, tries=2, timeout=25):
    """GET with bounded retries. Raises on final failure — scan.py catches
    per-source so one broken source never stops the scan."""
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(2 * (i + 1))
    raise last


def _salary(smin, smax):
    if smin and smax:
        return f"${int(smin):,} - ${int(smax):,}"
    return None


# ---------------------------------------------------------------- RemoteOK
def fetch_remoteok(cfg):
    out = []
    for j in get("https://remoteok.com/api").json():
        if not isinstance(j, dict) or not j.get("position"):
            continue  # element 0 is a legal notice
        try:
            posted = datetime.fromisoformat(str(j["date"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        smin = j.get("salary_min") or None
        out.append({
            "title": j["position"], "company": j.get("company") or "",
            "location": j.get("location") or "Remote", "remote": True,
            "salary": _salary(smin, j.get("salary_max")),
            "salary_min": int(smin) if smin else None,
            "url": j.get("url") or "",
            "description": strip_html(j.get("description") or "")[:1200],
            "posted_at": posted,
        })
    return out


# ---------------------------------------------------------------- Remotive
def fetch_remotive(cfg):
    out = []
    for j in get("https://remotive.com/api/remote-jobs?limit=100").json().get("jobs", []):
        try:
            posted = datetime.fromisoformat(j["publication_date"])
        except (KeyError, ValueError):
            continue
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        out.append({
            "title": j.get("title") or "", "company": j.get("company_name") or "",
            "location": j.get("candidate_required_location") or "Remote",
            "remote": True, "salary": j.get("salary") or None, "salary_min": None,
            "url": j.get("url") or "",
            "description": strip_html(j.get("description") or "")[:1200],
            "posted_at": posted,
        })
    return out


# ---------------------------------------------------------------- Jobicy
def fetch_jobicy(cfg):
    out = []
    r = get("https://jobicy.com/api/v2/remote-jobs?count=100&geo=usa")
    for j in r.json().get("jobs", []):
        try:
            posted = datetime.fromisoformat(str(j["pubDate"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        smin = j.get("annualSalaryMin") or None
        out.append({
            "title": j.get("jobTitle") or "", "company": j.get("companyName") or "",
            "location": j.get("jobGeo") or "Remote", "remote": True,
            "salary": _salary(smin, j.get("annualSalaryMax")),
            "salary_min": int(smin) if smin else None,
            "url": j.get("url") or "",
            "description": strip_html(j.get("jobExcerpt") or j.get("jobDescription") or "")[:1200],
            "posted_at": posted,
        })
    return out


# ------------------------------------------------------- WeWorkRemotely RSS
def fetch_weworkremotely(cfg):
    out = []
    root = ET.fromstring(get("https://weworkremotely.com/remote-jobs.rss").text)
    for item in root.iter("item"):
        raw_title = item.findtext("title") or ""
        company, sep, title = raw_title.partition(": ")
        if not sep:
            company, title = "", raw_title
        try:
            posted = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        out.append({
            "title": title.strip(), "company": company.strip(),
            "location": (item.findtext("region") or "Remote").strip(),
            "remote": True, "salary": None, "salary_min": None,
            "url": (item.findtext("link") or "").strip(),
            "description": strip_html(item.findtext("description") or "")[:1200],
            "posted_at": posted,
        })
    return out


# ------------------------------------------------- Greenhouse company boards
def _companies(kind):
    try:
        return json.loads((ROOT / "companies.json").read_text(encoding="utf-8-sig")).get(kind, [])
    except FileNotFoundError:
        return []


def fetch_greenhouse(cfg):
    """Lists each configured board, then fetches full detail only for postings
    fresh enough to matter, so large boards stay cheap."""
    max_h = cfg.get("store_max_age_hours", 24)
    now = datetime.now(timezone.utc)
    out = []
    for board in _companies("greenhouse"):
        try:
            jobs = get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs").json().get("jobs", [])
        except Exception as e:
            print(f"  greenhouse/{board}: {type(e).__name__}: {e}")
            continue
        fresh = []
        for j in jobs:
            try:
                upd = datetime.fromisoformat(j["updated_at"])
            except (KeyError, ValueError):
                continue
            if (now - upd).total_seconds() / 3600 <= max_h:
                fresh.append((j, upd))
        for j, upd in fresh[:15]:
            desc = ""
            try:
                detail = get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{j['id']}").json()
                desc = strip_html(detail.get("content") or "")[:1200]
            except Exception:
                pass
            out.append({
                "title": j.get("title") or "",
                "company": board.replace("-", " ").title(),
                "location": (j.get("location") or {}).get("name") or "",
                "remote": None,  # detected from text by the scorer
                "salary": None, "salary_min": None,
                "url": j.get("absolute_url") or "",
                "description": desc, "posted_at": upd,
            })
    return out


# ------------------------------------------------------ Lever company boards
def fetch_lever(cfg):
    max_h = cfg.get("store_max_age_hours", 24)
    now = datetime.now(timezone.utc)
    out = []
    for c in _companies("lever"):
        try:
            jobs = get(f"https://api.lever.co/v0/postings/{c}?mode=json&limit=100").json()
        except Exception as e:
            print(f"  lever/{c}: {type(e).__name__}: {e}")
            continue
        if not isinstance(jobs, list):
            continue
        for j in jobs:
            try:
                posted = datetime.fromtimestamp(j["createdAt"] / 1000, tz=timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            if (now - posted).total_seconds() / 3600 > max_h:
                continue
            loc = (j.get("categories") or {}).get("location") or ""
            out.append({
                "title": j.get("text") or "", "company": c.replace("-", " ").title(),
                "location": loc,
                "remote": j.get("workplaceType") == "remote" or "remote" in loc.lower(),
                "salary": None, "salary_min": None,
                "url": j.get("hostedUrl") or "",
                "description": strip_html(j.get("descriptionPlain") or "")[:1200],
                "posted_at": posted,
            })
    return out


# Registry: name -> fetch function. Add new sources here.
SOURCES = {
    "remoteok": fetch_remoteok,
    "remotive": fetch_remotive,
    "jobicy": fetch_jobicy,
    "weworkremotely": fetch_weworkremotely,
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
}
