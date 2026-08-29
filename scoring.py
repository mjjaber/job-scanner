"""Match scoring. Produces a BASE score (title + keywords + remote + shift
bonuses). The dashboard adds recency points in the browser, so ranking decays
naturally as a job ages between scans."""
import difflib
import re
from pathlib import Path

_titles = []          # normalized known titles as strings
_title_tokens = []    # (normalized string, token set)


def _norm_tokens(s):
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).split()


def load_titles(path):
    global _titles, _title_tokens
    seen, toks_list = set(), []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = re.sub(r"^\d+\.\s*", "", line.strip())
        if not line or "=" in line or line.isupper():
            continue  # blank lines, dividers, section headers, TOTAL line
        toks = tuple(_norm_tokens(line))
        if toks and toks not in seen:
            seen.add(toks)
            toks_list.append(toks)
    _title_tokens = [(" ".join(t), set(t)) for t in toks_list]
    _titles = [t[0] for t in _title_tokens]
    return len(_titles)


def title_match(job_title):
    jt = " ".join(_norm_tokens(job_title))
    if not jt:
        return 0
    if jt in _titles:
        return 40
    jset = set(jt.split())
    # a known title fully contained in the job title, e.g. "Senior Azure Cloud
    # Engineer II (Remote)" contains "azure cloud engineer"
    for _, toks in _title_tokens:
        if toks <= jset:
            return 34
    if difflib.get_close_matches(jt, _titles, n=1, cutoff=0.8):
        return 28
    if difflib.get_close_matches(jt, _titles, n=1, cutoff=0.62):
        return 16
    return 0


KEYWORDS = [
    (10, ["nerdio"]),
    (8, ["azure virtual desktop", "avd", "virtual desktop", "vdi",
         "end user computing", "euc", "citrix"]),
    (8, ["azure"]),
    (7, ["cmmc", "nist", "fedramp", "azure government", "gcc high",
         "government cloud", "gov cloud"]),
    (6, ["microsoft 365", "m365", "intune", "endpoint manager", "entra",
         "office 365", "modern workplace"]),
    (6, ["sql server", "azure sql", "t-sql", "tsql", "dba", "database", "sql"]),
    (6, ["data engineer", "etl", "data warehouse", "databricks", "synapse",
         "data factory", "microsoft fabric", "power bi", "data platform",
         "data lake", "data pipeline"]),
    (5, ["cloud security", "security engineer", "devops", "terraform",
         "infrastructure as code", "bicep", "site reliability"]),
    (4, ["technical account manager", "cloud support", "support engineer",
         "noc", "soc"]),
    (4, ["cloud"]),
]

SHIFT_TERMS = {
    "weekend": ["weekend", "weekends", "saturday", "sunday", "weekend shift",
                "weekend coverage"],
    "evening": ["evening shift", "evenings", "after hours", "after-hours",
                "afterhours", "off hours", "off-hours", "extended hours",
                "non standard hours", "non-standard hours", "late shift"],
    "night": ["night shift", "overnight", "night support", "third shift",
              "3rd shift", "graveyard shift"],
    "swing": ["swing shift", "second shift", "2nd shift"],
    "oncall": ["on call", "on-call", "on call rotation", "24x7", "24/7",
               "follow the sun"],
    "ops": ["noc", "soc", "operations center", "shift work"],
}
SHIFT_POINTS = {"weekend": 50, "night": 30, "swing": 30, "evening": 25,
                "oncall": 15, "ops": 15}
AFTER_HOURS_TAGS = {"evening", "night", "swing", "oncall"}

_word_rx_cache = {}


def _has_term(text, term):
    rx = _word_rx_cache.get(term)
    if rx is None:
        rx = _word_rx_cache[term] = re.compile(
            r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])")
    return rx.search(text) is not None


def keyword_score(text):
    s = 0
    for pts, terms in KEYWORDS:
        if any(_has_term(text, t) for t in terms):
            s += pts
    return min(s, 25)


def shift_info(text):
    tags = [tag for tag, terms in SHIFT_TERMS.items()
            if any(_has_term(text, t) for t in terms)]
    score = min(100, sum(SHIFT_POINTS[t] for t in tags))
    return score, tags


REMOTE_RX = re.compile(r"\bremote\b|work from home|\bwfh\b|\banywhere\b", re.I)
NON_US_RX = re.compile(r"\b(europe|emea|uk only|united kingdom|canada only|apac|"
                       r"asia|india|latam|australia|germany|poland)\b(?!.*united states)",
                       re.I)


def score_job(j, cfg):
    """Returns dict with base score, shift_score, shift_tags, remote flag."""
    text = f"{j.get('title', '')} {j.get('description', '')} {j.get('location', '')}".lower()
    base = title_match(j.get("title", ""))
    base += keyword_score(text)

    remote = bool(j.get("remote")) or REMOTE_RX.search(text) is not None
    if remote:
        base += 8

    loc = (j.get("location") or "").lower()
    if cfg.get("country", "").upper() == "US" and NON_US_RX.search(loc):
        base -= 20  # restricted to a non-US region

    shift_score, tags = shift_info(text)
    if "weekend" in tags:
        base += cfg.get("weekend_priority", 15)
    if AFTER_HOURS_TAGS & set(tags):
        base += cfg.get("after_hours_priority", 10)

    return {"score": max(0, min(100, base)), "shift_score": shift_score,
            "shift_tags": tags, "remote": remote}
