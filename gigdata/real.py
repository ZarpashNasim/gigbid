"""Real-data loader: Kaggle Upwork CSVs -> normalised, redacted, deduplicated job records.

We have NOT seen the real Kaggle files' columns (they could not be fetched from the dev sandbox), so column
mapping is alias-based and overridable. ALWAYS run the schema report first and read it:

    python -m gigdata.real schema --source upwork_50k_2024
    python -m gigdata.real build  --sources upwork_50k_2024,upwork_60k --limit 20000
    python -m gigdata.real stats  --sources contracts_1_3m

Raw CSVs go in data/raw/<source_key>/ (git-ignored). Outputs go to data/processed/ (git-ignored: licences unverified).
Every output record carries origin="real", its source key, and a per-field provenance map.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import yaml

from gigdata.text import detect_signals, fingerprint, redact

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OVERRIDES = ROOT / "data" / "column_overrides.yaml"      # optional: {source_key: {field: "Actual Column"}}

# canonical field -> accepted (normalised) header names
ALIASES: dict[str, list[str]] = {
    "job_id": ["job_id", "id", "uid", "ciphertext", "jobid", "job_uid", "posting_id"],
    "title": ["title", "job_title", "name", "job_name", "heading"],
    "description": ["description", "job_description", "desc", "details", "job_details", "text", "body", "content"],
    "skills": ["skills", "skill", "skill_list", "skills_required", "required_skills", "tags", "key_skills", "categories"],
    "budget": ["budget", "fixed_budget", "fixed_price", "amount", "budget_usd", "budget_amount", "price", "fixed_price_budget"],
    "hourly_min": ["hourly_min", "hourly_low", "hourly_rate_min", "min_hourly_rate", "hourly_range_min", "hourly_rate_low", "min_rate"],
    "hourly_max": ["hourly_max", "hourly_high", "hourly_rate_max", "max_hourly_rate", "hourly_range_max", "hourly_rate_high", "max_rate"],
    "duration": ["duration", "project_length", "duration_label", "engagement_duration", "length"],
    "experience_level": ["experience_level", "contractor_tier", "tier", "experience", "level"],
    "published": ["published", "posted", "date", "created", "publish_time", "date_posted", "published_date", "created_on"],
    "client_country": ["client_country", "country", "buyer_country", "client_location"],
    "client_spent": ["client_total_spent", "total_spent", "client_spent", "buyer_total_spent"],
    "client_rating": ["client_rating", "client_feedback_score", "buyer_rating", "feedback_score"],
    "client_payment_verified": ["payment_verified", "client_payment_verified", "buyer_payment_verified"],
}
REQUIRED = ["title", "description"]


def norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(h).strip().lower()).strip("_")


def source_dir(key: str, raw_dir: Path = RAW) -> Path:
    return raw_dir / key


def list_csvs(key: str, raw_dir: Path = RAW) -> list[Path]:
    d = source_dir(key, raw_dir)
    return sorted(d.glob("*.csv")) if d.exists() else []


def load_overrides(key: str, path: Path = OVERRIDES) -> dict[str, str]:
    if path.exists():
        return (yaml.safe_load(path.read_text()) or {}).get(key, {}) or {}
    return {}


def map_columns(columns: list[str], overrides: dict[str, str] | None = None) -> dict[str, str]:
    """canonical field -> actual column name. Exact (normalised) alias match only: no fuzzy guessing."""
    overrides = overrides or {}
    by_norm = {norm_header(c): c for c in columns}
    mapping: dict[str, str] = {}
    for field, names in ALIASES.items():
        if field in overrides and overrides[field] in columns:
            mapping[field] = overrides[field]
            continue
        for n in names:
            if n in by_norm:
                mapping[field] = by_norm[n]
                break
    return mapping


def schema_report(key: str, raw_dir: Path = RAW) -> dict:
    files = list_csvs(key, raw_dir)
    if not files:
        return {"source": key, "error": f"no CSV files in {source_dir(key, raw_dir)}"}
    head = pd.read_csv(files[0], nrows=200, dtype=str, on_bad_lines="skip", encoding_errors="replace")
    mapping = map_columns(list(head.columns), load_overrides(key))
    unmapped = [c for c in head.columns if c not in mapping.values()]
    missing_required = [f for f in REQUIRED if f not in mapping]
    return {"source": key, "files": [f.name for f in files], "columns": list(head.columns),
            "mapped": mapping, "unmapped_columns": unmapped, "missing_required": missing_required,
            "sample_row": {k: (str(v)[:80] if pd.notna(v) else None) for k, v in head.iloc[0].items()} if len(head) else {},
            "action": ("OK" if not missing_required else
                       f"Add overrides to {OVERRIDES.name}: {{{key}: {{{', '.join(f'{f}: <column>' for f in missing_required)}}}}}")}


# ---------------------------------------------------------------- value parsing
MONEY = re.compile(r"(\d[\d,]*\.?\d*)\s*([kK])?")


def parse_money(x) -> float | None:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    m = MONEY.search(str(x).replace("$", " "))
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v * 1000 if m.group(2) else v


def parse_money_range(x) -> tuple[float | None, float | None]:
    nums = [parse_money(m.group(0)) for m in MONEY.finditer(str(x).replace("$", " "))] if x is not None else []
    nums = [n for n in nums if n is not None]
    return (nums[0], nums[-1]) if nums else (None, None)


def parse_skills(x) -> list[str]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return []
    s = str(x).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            return [str(i).strip() for i in json.loads(s.replace("'", '"')) if str(i).strip()]
        except Exception:   # noqa: BLE001
            s = s.strip("[]")
    parts = re.split(r"[|;,\n]", s)
    return [p.strip().strip("'\"") for p in parts if p.strip().strip("'\"")]


DURATION_DAYS = [(r"less than (a|1) month|< ?1 month", 21), (r"1 to 3 months|1-3 months", 60),
                 (r"3 to 6 months|3-6 months", 135), (r"more than 6 months|6\+ months|> ?6 months", 210),
                 (r"week", 7), (r"day", 3)]


def parse_duration_days(x) -> int | None:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).lower()
    for pat, d in DURATION_DAYS:
        if re.search(pat, s):
            return d
    return None


def connects_cost_for(job_id: str) -> int:
    """Connects cost is not part of public job-post data; assign deterministically (SYNTHETIC, documented)."""
    return (8, 12, 16)[int(hashlib.sha256(job_id.encode()).hexdigest(), 16) % 3]


def english_ratio(text: str) -> float:
    return sum(c.isascii() for c in text) / max(len(text), 1)


# ---------------------------------------------------------------- normalisation
def normalise_row(row: dict, mapping: dict[str, str], source: str, idx: int, min_desc: int = 80,
                  min_ascii: float = 0.85) -> tuple[dict | None, str | None, int]:
    """Returns (record | None, drop_reason | None, redaction_count)."""
    g = lambda f: row.get(mapping[f]) if f in mapping else None
    title, desc = g("title"), g("description")
    if not isinstance(title, str) or not title.strip():
        return None, "missing_title", 0
    if not isinstance(desc, str) or len(desc.strip()) < min_desc:
        return None, "description_too_short", 0
    if english_ratio(title + desc) < min_ascii:
        return None, "mostly_non_ascii", 0
    raw_text = f"{title}\n{desc}"
    signals = detect_signals(raw_text)             # detect BEFORE redaction (redaction removes contact details)
    t, r1 = redact(title.strip())
    d, r2 = redact(desc.strip())
    if re.search(r"\[(EMAIL|PHONE)\]", d + t):
        signals = sorted(set(signals) | {"contact_details_in_post"})
    raw_id = g("job_id")
    jid = f"{source}:{raw_id}" if isinstance(raw_id, str) and raw_id.strip() else f"{source}:row{idx}"

    hmin, hmax = parse_money(g("hourly_min")), parse_money(g("hourly_max"))
    bmin, bmax = parse_money_range(g("budget"))
    if hmin is not None or hmax is not None:
        pricing, lo, hi = "hourly", hmin, hmax if hmax is not None else hmin
    elif bmin is not None:
        pricing, lo, hi = "fixed", bmin, bmax
    else:
        pricing, lo, hi = "unknown", None, None
    prov = {"title": "real", "description": "real(redacted)", "required_skills": "real" if "skills" in mapping else "absent",
            "budget": "real" if pricing != "unknown" else "absent", "connects_cost": "synthetic(deterministic hash)",
            "warning_signals": "rule-derived(weak label)", "screening_questions": "absent"}
    rec = {
        "job_id": jid, "origin": "real", "source": source, "title": t, "description": d,
        "required_skills": parse_skills(g("skills")), "pricing_type": pricing,
        "budget": {"min": lo, "max": hi, "currency": "USD"},
        "duration_days": parse_duration_days(g("duration")), "experience_level": g("experience_level"),
        "published": g("published"), "client_country": g("client_country"),
        "screening_questions": [], "warning_signals": signals, "connects_cost": connects_cost_for(jid),
        "provenance": prov,
    }
    return rec, None, r1 + r2


def build_jobs(keys: list[str], limit: int | None = None, raw_dir: Path = RAW, out_dir: Path = PROCESSED,
               chunksize: int = 50_000) -> dict:
    """Stream CSVs, normalise, dedupe across sources, write jobs_real.jsonl + a manifest of every drop."""
    out_dir.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    manifest: dict = {"sources": {}, "rows_out": 0}
    out = (out_dir / "jobs_real.jsonl").open("w")
    for key in keys:
        files = list_csvs(key, raw_dir)
        stats = {"files": [f.name for f in files], "rows_in": 0, "dropped": Counter(), "redactions": 0,
                 "signals": Counter(), "kept": 0}
        if not files:
            stats["error"] = "no CSV files found"
        for f in files:
            mapping = None
            idx = 0
            for chunk in pd.read_csv(f, dtype=str, chunksize=chunksize, on_bad_lines="skip", encoding_errors="replace"):
                if mapping is None:
                    mapping = map_columns(list(chunk.columns), load_overrides(key))
                    if any(r not in mapping for r in REQUIRED):
                        stats["error"] = f"missing required columns {[r for r in REQUIRED if r not in mapping]}; run schema"
                        break
                    stats["mapped"] = mapping
                for row in chunk.to_dict("records"):
                    idx += 1
                    stats["rows_in"] += 1
                    rec, why, nred = normalise_row(row, mapping, key, idx)
                    if rec is None:
                        stats["dropped"][why] += 1
                        continue
                    fp = fingerprint(rec["title"], rec["description"])
                    if fp in seen:
                        stats["dropped"]["duplicate"] += 1
                        continue
                    seen.add(fp)
                    stats["redactions"] += nred
                    stats["signals"].update(rec["warning_signals"])
                    out.write(json.dumps(rec) + "\n")
                    stats["kept"] += 1
                    manifest["rows_out"] += 1
                    if limit and manifest["rows_out"] >= limit:
                        break
                if limit and manifest["rows_out"] >= limit:
                    break
        stats["dropped"], stats["signals"] = dict(stats["dropped"]), dict(stats["signals"])
        manifest["sources"][key] = stats
    out.close()
    (out_dir / "jobs_real.manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


# ---------------------------------------------------------------- market statistics (Pricing agent)
def build_market_stats(keys: list[str], raw_dir: Path = RAW, out_dir: Path = PROCESSED, min_n: int = 30,
                       chunksize: int = 100_000) -> dict:
    """Median/quartile hourly and fixed budgets per skill. Reads any source with budget/hourly/skills columns."""
    hourly: dict[str, list[float]] = defaultdict(list)
    fixed: dict[str, list[float]] = defaultdict(list)
    n_rows = 0
    for key in keys:
        for f in list_csvs(key, raw_dir):
            mapping = None
            for chunk in pd.read_csv(f, dtype=str, chunksize=chunksize, on_bad_lines="skip", encoding_errors="replace"):
                mapping = mapping or map_columns(list(chunk.columns), load_overrides(key))
                for row in chunk.to_dict("records"):
                    n_rows += 1
                    skills = parse_skills(row.get(mapping["skills"])) if "skills" in mapping else ["(all)"]
                    skills = skills[:6] + ["(all)"]
                    hmin = parse_money(row.get(mapping["hourly_min"])) if "hourly_min" in mapping else None
                    hmax = parse_money(row.get(mapping["hourly_max"])) if "hourly_max" in mapping else None
                    b, _ = parse_money_range(row.get(mapping["budget"])) if "budget" in mapping else (None, None)
                    for s in skills:
                        s = s.lower()
                        if hmin and hmax and 3 <= hmin <= 500:
                            hourly[s].append((hmin + hmax) / 2)
                        elif b and 5 <= b <= 200_000:
                            fixed[s].append(b)
    q = lambda xs: {"n": len(xs), "p25": statistics.quantiles(xs, n=4)[0], "median": statistics.median(xs),
                    "p75": statistics.quantiles(xs, n=4)[2]}
    stats = {"rows_scanned": n_rows, "min_n": min_n,
             "hourly": {s: q(v) for s, v in hourly.items() if len(v) >= min_n},
             "fixed": {s: q(v) for s, v in fixed.items() if len(v) >= min_n}}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "market_stats.json").write_text(json.dumps(stats, indent=2))
    return stats


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("schema"); s.add_argument("--source", required=True)
    b = sub.add_parser("build"); b.add_argument("--sources", required=True); b.add_argument("--limit", type=int)
    t = sub.add_parser("stats"); t.add_argument("--sources", required=True)
    a = ap.parse_args()
    if a.cmd == "schema":
        print(json.dumps(schema_report(a.source), indent=2))
    elif a.cmd == "build":
        print(json.dumps(build_jobs(a.sources.split(","), a.limit), indent=2, default=str))
    else:
        r = build_market_stats(a.sources.split(","))
        print(f"scanned {r['rows_scanned']} rows; hourly skills: {len(r['hourly'])}, fixed skills: {len(r['fixed'])}")


if __name__ == "__main__":
    main()
