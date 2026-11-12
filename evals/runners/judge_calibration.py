"""Judge calibration: you label 30 items yourself, the LLM judge labels the same 30, report Cohen's kappa.

python -m evals.runners.judge_calibration --human evals/datasets/human_labels.json --judge evals/results/judge_labels.json
Both files: {"<item_id>": "pass"|"fail"|...}. Report disagreements too (viva question 8).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.runners.metrics import cohen_kappa


def calibrate(human: dict, judge: dict) -> dict:
    ids = sorted(set(human) & set(judge))
    k = cohen_kappa([human[i] for i in ids], [judge[i] for i in ids])
    return {"n": len(ids), "kappa": k, "disagreements": [i for i in ids if human[i] != judge[i]]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--human", required=True)
    ap.add_argument("--judge", required=True)
    ap.add_argument("--out", default="evals/results/judge_calibration.json")
    a = ap.parse_args()
    res = calibrate(json.loads(Path(a.human).read_text()), json.loads(Path(a.judge).read_text()))
    Path(a.out).write_text(json.dumps(res, indent=2))
    print(res)
