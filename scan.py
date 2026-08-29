"""One scan cycle: fetch due sources, score, dedupe, merge with the previous
results, write docs/data/jobs.json. Run by GitHub Actions on a schedule, or
locally with `python scan.py`."""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import scoring
import sources

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "data" / "jobs.json"


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))


def dedupe_key(title, company):
    n = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())
    return f"{n(company)}|{n(title)}"


def load_previous():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"jobs": [], "source_meta": {}}


def due_sources(cfg, meta, now):
    """A source runs only when its configured interval has elapsed since its
    last successful run — lets slow-moving APIs (Remotive) be polled gently
    even though the workflow itself fires every few minutes."""
    names = []
    for name in sources.SOURCES:
        scfg = cfg.get("sources", {}).get(name, {})
        if not scfg.get("enabled", True):
            continue
        last = (meta.get(name) or {}).get("last_run")
        if last:
            elapsed_min = (now - datetime.fromisoformat(last)).total_seconds() / 60
            # 0.85 fudge: workflow cron jitter shouldn't make a source skip a cycle
            if elapsed_min < scfg.get("interval_minutes", 10) * 0.85:
                continue
        names.append(name)
    return names


def run_source(name, cfg):
    try:
        raws = sources.SOURCES[name](cfg)
        return name, raws, None
    except Exception as e:
        return name, [], f"{type(e).__name__}: {e}"


def main():
    cfg = load_config()
    n_titles = scoring.load_titles(ROOT / cfg.get("job_titles_file", "job_titles.txt"))
    print(f"loaded {n_titles} job titles")

    now = datetime.now(timezone.utc)
    prev = load_previous()
    meta = prev.get("source_meta", {})
    jobs = {j["id"]: j for j in prev.get("jobs", [])}

    names = due_sources(cfg, meta, now)
    print(f"scanning: {', '.join(names) or '(none due)'}")

    max_h = cfg.get("store_max_age_hours", 24)
    total_new = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = ex.map(lambda n: run_source(n, cfg), names)
    for name, raws, err in results:
        m = {"last_run": now.isoformat(), "found": 0, "new": 0, "error": err}
        if err:
            print(f"  {name}: FAILED {err}")
            m["last_run"] = (meta.get(name) or {}).get("last_run")  # retry next cycle
            meta[name] = {**(meta.get(name) or {}), "error": err}
            continue
        for raw in raws:
            posted = raw.get("posted_at")
            if not posted:
                continue
            age_h = (now - posted).total_seconds() / 3600
            if age_h > max_h or age_h < -1:
                continue
            m["found"] += 1
            sc = scoring.score_job(raw, cfg)
            if cfg.get("remote_only") and not sc["remote"]:
                continue
            if sc["score"] < cfg.get("min_score", 0):
                continue
            key = dedupe_key(raw["title"], raw["company"])
            if key in jobs:
                ex_job = jobs[key]
                if name != ex_job["source"] and name not in ex_job["other_sources"]:
                    ex_job["other_sources"].append(name)
                continue
            jobs[key] = {
                "id": key,
                "title": raw["title"], "company": raw["company"],
                "location": raw["location"], "remote": sc["remote"],
                "salary": raw.get("salary"), "salary_min": raw.get("salary_min"),
                "url": raw.get("url") or "",
                "source": name, "other_sources": [],
                "description": (raw.get("description") or "")[:600],
                "posted_at": posted.isoformat(),
                "first_seen": now.isoformat(),
                "score": sc["score"], "shift_score": sc["shift_score"],
                "shift_tags": sc["shift_tags"],
            }
            m["new"] += 1
        total_new += m["new"]
        meta[name] = m
        print(f"  {name}: {m['found']} fresh, {m['new']} new")

    # prune anything older than the store window
    kept = [j for j in jobs.values()
            if (now - datetime.fromisoformat(j["posted_at"])).total_seconds() / 3600 <= max_h]
    kept.sort(key=lambda j: j["posted_at"], reverse=True)

    out = {
        "generated_at": now.isoformat(),
        "config": {
            "max_age_hours": cfg.get("max_age_hours", 4),
            "notification_threshold": cfg.get("notification_threshold", 70),
        },
        "source_meta": meta,
        "jobs": kept,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"wrote {len(kept)} jobs ({total_new} new) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
