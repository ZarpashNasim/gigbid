"""Human audit of the rule detector on REAL posts: the only non-circular check of rule quality we can run.

1.  python -m gigdata.audit sample --n 60          writes data/processed/audit_sample.csv (30 flagged + 30 unflagged)
2.  Open the CSV, fill the `human_label` column with  scam | injection | legit  for each row (about 30 minutes).
3.  python -m gigdata.audit score                  precision of the flags, and the miss rate among unflagged posts.

The same labelled rows can seed the judge-calibration set (30 items you label vs the LLM judge).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"
BAD = {"scam", "injection"}


def sample(n: int, seed: int = 11, jobs_path: Path = PROCESSED / "jobs_real.jsonl", out: Path = PROCESSED / "audit_sample.csv") -> dict:
    jobs = [json.loads(l) for l in jobs_path.read_text().splitlines()]
    flagged = [j for j in jobs if set(j["warning_signals"]) - {"contact_details_in_post"}]
    clean = [j for j in jobs if not set(j["warning_signals"]) - {"contact_details_in_post"}]
    rng = random.Random(seed)
    k_f = min(n // 2, len(flagged))                 # half flagged; top up from the other group if one is small
    k_c = min(n - k_f, len(clean))
    pick = rng.sample(flagged, k_f) + rng.sample(clean, k_c)
    rng.shuffle(pick)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["job_id", "title", "description_excerpt", "rule_flags", "human_label"])
        for j in pick:
            w.writerow([j["job_id"], j["title"], j["description"][:700].replace("\n", " "), "|".join(j["warning_signals"]), ""])
    return {"flagged_population": len(flagged), "unflagged_population": len(clean), "sampled": len(pick), "file": str(out)}


def score(path: Path = PROCESSED / "audit_sample.csv", pops: dict | None = None) -> dict:
    rows = [r for r in csv.DictReader(path.open(encoding="utf-8")) if r["human_label"].strip()]
    if not rows:
        return {"error": "no labelled rows: fill human_label with scam|injection|legit"}
    is_flag = lambda r: bool(set(filter(None, r["rule_flags"].split("|"))) - {"contact_details_in_post"})
    fl, un = [r for r in rows if is_flag(r)], [r for r in rows if not is_flag(r)]
    bad = lambda r: r["human_label"].strip().lower() in BAD
    out = {"n_labelled": len(rows),
           "flag_precision": (sum(map(bad, fl)) / len(fl)) if fl else None, "n_flagged_sampled": len(fl),
           "miss_rate_among_unflagged": (sum(map(bad, un)) / len(un)) if un else None, "n_unflagged_sampled": len(un)}
    if pops and out["flag_precision"] is not None and out["miss_rate_among_unflagged"] is not None:
        tp = out["flag_precision"] * pops["flagged_population"]          # stratified estimate over the full real set
        fn = out["miss_rate_among_unflagged"] * pops["unflagged_population"]
        out["estimated_recall"] = tp / (tp + fn) if tp + fn else None
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample"); s.add_argument("--n", type=int, default=60)
    sub.add_parser("score")
    a = ap.parse_args()
    print(json.dumps(sample(a.n) if a.cmd == "sample" else score(), indent=2))
