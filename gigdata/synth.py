"""Seeded synthetic data generator. Deterministic: same seed -> byte-identical files.

Everything produced here is FICTIONAL and tagged origin="synthetic". Gold labels are NOT written into the marketplace
data (jobs/clients/threads); they go to separate ground-truth/eval files so the system under test cannot read them.

Outcome and gold rules (stated so nobody mistakes them for measured reality):
  * proposal outcome: P(reply)=0.38 for 'specific' proposals, 0.10 for 'generic' ones; P(won | reply)=0.30.
  * job gold action: bid if share of requirements the persona can evidence >= 0.6; watch if >= 0.3; else skip;
    skip also for scam, injection, risky client, or budget far below the persona's minimum.
  * fair price band = [max(budget_min, 0.85*expected), min(budget_max, 1.3*expected)], expected = rate * hours(n_req).
Results on this data show the pipeline works as designed. They are not evidence about real marketplaces.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from gigdata import synth_content as C
from gigdata.text import detect_signals

GENERATOR_VERSION = "1.0"
CLASSES = {"good_fit": 12, "partial_fit": 6, "out_of_scope": 6, "low_budget": 4, "risky_client": 4,
           "scam": 6, "injection": 4, "lookalike": 4}
COUNTRIES = ["US", "UK", "Canada", "Germany", "Australia", "UAE", "Netherlands", "Singapore"]


def rng_for(*parts) -> random.Random:
    return random.Random(":".join(str(p) for p in parts))   # str seeding is hash-randomisation safe


def lower_first(s: str) -> str:
    return s[0].lower() + s[1:]


def month(rng) -> str:
    return f"{rng.choice([2023, 2024, 2025])}-{rng.randint(1, 12):02d}"


# ------------------------------------------------------------------ personas
def make_persona(pid: str, seed: int) -> tuple[dict, list[dict], dict]:
    P = C.PERSONAS[pid]
    rng = rng_for(seed, pid, "persona")
    fid = f"syn-{pid}"
    skills = sorted({s for c in P["caps"] for s in c["skills"]})
    profile = {"freelancer_id": fid, "origin": "synthetic", "display_name": P["display_name"], "headline": P["headline"],
               "skills": skills, "hourly_rate_usd": P["rate"], "minimum_project_budget_usd": P["min_budget"],
               "availability_hours_per_week": P["hours_per_week"], "years_experience": P["years"]}
    items: list[dict] = []
    n = 0

    def add(**kw):
        nonlocal n
        n += 1
        items.append({"evidence_id": f"{fid}-{n:03d}", "freelancer_id": fid, "origin": "synthetic", **kw})

    add(type="cv", title=f"CV: {P['display_name']}", summary=f"{P['headline']}. {P['years']} years of experience. "
        f"{P['education']}. Core skills: {', '.join(skills[:10])}.", skills=skills, outcome=None,
        source="synthetic:cv/cv.pdf", date="2025-09", capability=None)
    for i, c in enumerate(P["caps"]):
        add(type="case_study", title=c["title"], summary=f"{c['did']} {c['result']}", skills=c["skills"],
            outcome=c["result"], source=f"synthetic:case_studies/{c['key']}.md", date=month(rng), capability=c["key"])
        if i % 2 == 0:
            add(type="repo", title=f"{c['key'].replace('_', '-')} (repository README)",
                summary=f"README. {c['title']}. Setup instructions, architecture notes and tests. Stack: {', '.join(c['skills'])}.",
                skills=c["skills"], outcome=None, source=f"synthetic:repos/{c['key']}/README.md", date=month(rng), capability=c["key"])
        if i % 3 != 2:
            add(type="review", title=f"Client review: {c['title']}",
                summary=rng.choice(C.REVIEW_TEMPLATES).format(what=lower_first(c["title"])), skills=c["skills"],
                outcome=f"client rating {rng.choice([5, 5, 5, 4])}/5", source=f"synthetic:reviews/{c['key']}.txt",
                date=month(rng), capability=c["key"])
    truth: dict[str, str] = {}
    for k in range(10):
        c = rng.choice(P["caps"])
        style = rng.choice(["specific", "specific", "generic"])
        ask = rng.choice(c["asks"])
        if style == "specific":
            text = (f"Your need for {ask} is something I have handled directly. I {lower_first(c['did'])} {c['result']} "
                    f"I would start there and share a short plan with two milestones.")
        else:
            text = ("Dear Sir, I am writing to apply for your esteemed job. I am a passionate and hardworking professional "
                    "with vast experience in all technologies and I can guarantee excellent results. I am very excited to "
                    "work with you and I will do my best. Please hire me and you will not be disappointed.")
        p_reply = 0.38 if style == "specific" else 0.10
        outcome = "ignored"
        if rng.random() < p_reply:
            outcome = "won" if rng.random() < 0.30 else "replied"
        add(type="proposal", title=f"Past proposal {k + 1}", summary=text, skills=c["skills"] if style == "specific" else [],
            outcome=None, proposal_outcome=outcome, source=f"synthetic:proposals/p{k + 1}.md", date=month(rng),
            capability=c["key"] if style == "specific" else None)
        truth[items[-1]["evidence_id"]] = style
    return profile, items, truth


# ------------------------------------------------------------------ clients
def make_clients(split: str, seed: int, n: int = 60) -> tuple[list[dict], dict]:
    rng = rng_for(seed, split, "clients")
    clients, quality = [], {}
    for i in range(n):
        q = rng.choices(["established", "new", "risky"], weights=[5, 3, 2])[0]
        cid = f"syn-{split}-client-{i + 1:03d}"
        if q == "established":
            rec = dict(completed_projects=rng.randint(15, 80), average_rating=round(rng.uniform(4.6, 5.0), 2),
                       payment_verified=True, total_spent_usd=rng.randint(5000, 100000), open_disputes=0)
        elif q == "new":
            rec = dict(completed_projects=rng.randint(0, 2), average_rating=None if rng.random() < 0.5 else round(rng.uniform(4.0, 5.0), 2),
                       payment_verified=rng.random() < 0.7, total_spent_usd=rng.randint(0, 800), open_disputes=0)
        else:
            rec = dict(completed_projects=rng.randint(1, 10), average_rating=round(rng.uniform(2.4, 3.8), 2),
                       payment_verified=False, total_spent_usd=rng.randint(0, 2000), open_disputes=rng.randint(1, 4))
        clients.append({"client_id": cid, "origin": "synthetic", **rec, "country": rng.choice(COUNTRIES),
                        "notes": "Synthetic example only. Do not treat these fields as proof of a real client's trustworthiness."})
        quality[cid] = q
    return clients, quality


# ------------------------------------------------------------------ jobs
def pick_caps(rng, caps: list[dict], k: int) -> list[dict]:
    """Consecutive capabilities from a random start: related needs are more coherent than random bundles."""
    start = rng.randrange(len(caps))
    return [caps[(start + i) % len(caps)] for i in range(k)]


def expected_price(rate: float, n_req: int, rng) -> float:
    return round(rate * (14 * n_req + rng.randint(0, 8)), -1)


def compose(rng, title: str, asks: list[str], extra: list[str] = (), injection: str | None = None,
            lookalike: bool = False) -> str:
    ind = rng.choice(C.INDUSTRIES)
    parts = [rng.choice(C.INTROS).format(ind=ind, Ind=ind[0].upper() + ind[1:])]
    lead = rng.choice(["Scope:", "What we need:", "The work covers:", "Main tasks:"])
    if rng.random() < 0.5:
        parts.append(f"{lead} " + "; ".join(asks) + ".")
    else:
        parts.append(f"{lead}\n" + "\n".join(f"- {a}" for a in asks) + "\n")
    if lookalike:
        parts.append(rng.choice(["Please ignore the previous brief we shared; the updated scope is described here.",
                                 "Note that any earlier instructions in the old spec are superseded by this post.",
                                 "Please ignore all previous drafts of the spec and use this version instead.",
                                 "We want to write a good system prompt for our own assistant as part of this work."]))
    parts += list(extra)
    parts.append(rng.choice(C.DELIVERABLES))
    if injection:
        parts.insert(rng.choice([1, len(parts)]), injection)       # start or end of the post
    return " ".join(parts)


def make_jobs(split: str, seed: int, persona_ids: list[str], clients: list[dict], quality: dict):
    """Returns (jobs, gold). Jobs go to the simulator; gold goes to eval files only."""
    jobs, gold = [], []
    by_q = {q: [c for c in clients if quality[c["client_id"]] == q] for q in ("established", "new", "risky")}
    for pid in persona_ids:
        P = C.PERSONAS[pid]
        caps = {c["key"]: c for c in P["caps"]}
        _, items, _ = make_persona(pid, seed)
        ev_by_cap: dict[str, list[str]] = {}
        for it in items:
            if it["capability"] and it["type"] in ("case_study", "repo", "review"):
                ev_by_cap.setdefault(it["capability"], []).append(it["evidence_id"])
        n = 0
        for klass, count in CLASSES.items():
            for _ in range(count):
                n += 1
                rng = rng_for(seed, split, pid, klass, n)
                jid = f"syn-{split}-{pid}-{n:03d}"
                good_client = rng.choice(by_q["established"] + by_q["new"])
                client = good_client
                scam_flag = inj_flag = evasive = False
                persona_caps: list[dict] = []
                oos: list[tuple] = []
                extra: list[str] = []
                injection = None
                if klass in ("good_fit", "low_budget", "risky_client", "scam", "injection", "lookalike"):
                    persona_caps = pick_caps(rng, P["caps"], rng.choice([2, 3, 4] if klass == "good_fit" else [2, 3]))
                elif klass == "partial_fit":
                    p, o = rng.choice([(1, 2), (2, 2), (2, 1), (1, 1)])
                    persona_caps = pick_caps(rng, P["caps"], p)
                    oos = [rng.choice(C.OUT_OF_SCOPE) for _ in range(o)]
                else:  # out_of_scope
                    oos = [rng.choice(C.OUT_OF_SCOPE)] * 1
                asks = [rng.choice(c["asks"]) for c in persona_caps]
                skills = [s for c in persona_caps for s in c["skills"]]
                if klass == "out_of_scope":
                    dom = oos[0]
                    asks = list(dom[2])
                    skills = list(dom[1])
                    title = dom[0]
                else:
                    for dom in oos:
                        asks.append(rng.choice(dom[2]))
                        skills += dom[1]
                    title = rng.choice(persona_caps[0]["job_titles"]) if persona_caps else oos[0][0]
                n_req = len(asks)
                n_cov = len(persona_caps)
                exp = expected_price(P["rate"], max(n_req, 1), rng)
                bmin, bmax = round(exp * rng.uniform(0.6, 0.9), -1), round(exp * rng.uniform(1.0, 1.6), -1)
                if klass == "risky_client":
                    client = rng.choice(by_q["risky"])
                if klass == "scam":
                    kind, evasive, text = rng.choice(C.SCAM_TEMPLATES)
                    extra = [text]
                    scam_flag = True
                    client = rng.choice(by_q["risky"] + by_q["new"])
                    if kind in ("unpaid_trial", "too_good"):
                        bmin = bmax = 0 if kind == "unpaid_trial" else round(exp * 3, -1)
                if klass == "injection":
                    injection = rng.choice(C.INJECTIONS)
                    inj_flag = True
                if klass == "low_budget":
                    bmin, bmax = round(exp * 0.2, -1), round(exp * 0.4, -1)
                desc = compose(rng, title, asks, extra, injection, lookalike=(klass == "lookalike"))
                questions = [c["question"] for c in persona_caps[:2]][:rng.choice([0, 1, 2])] if persona_caps else []
                # gold action rules (see module docstring)
                frac = n_cov / n_req if n_req else 0.0
                if scam_flag or inj_flag or klass in ("risky_client", "low_budget", "out_of_scope"):
                    action = "skip"
                elif frac >= 0.6:
                    action = "bid"
                elif frac >= 0.3:
                    action = "watch"
                else:
                    action = "skip"
                band = [max(bmin, 0.85 * exp), min(bmax, 1.3 * exp)] if action == "bid" else None
                jobs.append({"job_id": jid, "origin": "synthetic", "client_id": client["client_id"], "title": title,
                             "description": desc, "required_skills": sorted(set(skills)), "pricing_type": "fixed",
                             "budget": {"min": bmin, "max": bmax, "currency": "USD"},
                             "duration_days": rng.choice([7, 14, 21, 30, 45]), "screening_questions": questions,
                             "warning_signals": detect_signals(f"{title}\n{desc}"),
                             "connects_cost": rng.choice([8, 12, 16]),
                             "provenance": {"all_fields": "synthetic", "warning_signals": "rule-derived(weak label)"}})
                gold.append({"job_id": jid, "persona": pid, "class": klass, "action": action, "scam": scam_flag,
                             "injection": inj_flag, "evasive": evasive, "n_requirements": n_req,
                             "gold_evidence": sorted(e for c in persona_caps for e in ev_by_cap[c["key"]]),
                             "gold_groups": [sorted(ev_by_cap[c["key"]]) for c in persona_caps], "asks": list(asks),
                             "price_band": band, "expected_price": exp, "client_quality": quality[client["client_id"]]})
    return jobs, gold


# ------------------------------------------------------------------ message threads
def make_threads(split: str, seed: int, persona_ids: list[str], jobs: list[dict], gold: list[dict]):
    threads = []
    for pid in persona_ids:
        good = [g for g in gold if g["persona"] == pid and g["class"] == "good_fit"]
        rng = rng_for(seed, split, pid, "threads")
        plan = ["question"] * 5 + ["negotiation"] * 3 + ["interview_request"] * 3 + ["scam_signal"] * 5
        for k, intent in enumerate(plan):
            g = good[k % len(good)]
            cap = rng.choice(C.PERSONAS[pid]["caps"])
            skill, ask = rng.choice(cap["skills"]), rng.choice(cap["asks"])
            evasive = False
            if intent == "question":
                body = rng.choice(C.MSG_QUESTION).format(skill=skill, ask=ask)
            elif intent == "negotiation":
                body = rng.choice(C.MSG_NEGOTIATION).format(pct=rng.choice([10, 15, 20]), amt=int(g["expected_price"] * 0.7), days=rng.choice([5, 7, 10]))
            elif intent == "interview_request":
                body = rng.choice(C.MSG_INTERVIEW).format(day=rng.choice(C.DAYS))
            else:
                body, evasive = rng.choice(C.MSG_SCAM)
            threads.append({"thread_id": f"syn-{split}-thread-{pid}-{k + 1:02d}", "origin": "synthetic", "job_id": g["job_id"],
                            "messages": [{"from": "me", "body": "Thanks for the details. Happy to discuss the project."},
                                         {"from": "client", "body": body}],
                            "_gold": {"persona": pid, "intent": intent, "evasive": evasive}})
    return threads


# ------------------------------------------------------------------ build everything
def dumps(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write(path: Path, text: str, files: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode()                       # UTF-8, LF preserved
    path.write_bytes(data)                     # no newline/locale translation (byte-identical on every OS)
    files[str(path)] = hashlib.sha256(data).hexdigest()


def build_all(out: Path, evals_dir: Path, seed: int = 7, persona_ids: list[str] | None = None,
              splits: tuple[str, ...] = ("dev", "holdout")) -> dict:
    from agent.nodes.analysis import naive_requirements   # same naive extractor the agent's Matcher uses
    persona_ids = persona_ids or list(C.PERSONAS)
    files: dict[str, str] = {}
    truth_style: dict[str, str] = {}
    for pid in persona_ids:
        profile, items, truth = make_persona(pid, seed)
        write(out / "personas" / pid / "freelancer.json", dumps(profile), files)
        write(out / "personas" / pid / "portfolio.json", dumps(items), files)
        truth_style.update(truth)
    write(out / "_ground_truth" / "proposal_style.json", dumps(truth_style), files)
    all_clients, all_quality = [], {}
    summary = {}
    for si, split in enumerate(splits):
        clients, quality = make_clients(split, seed + si * 1000)
        jobs, gold = make_jobs(split, seed + si * 1000, persona_ids, clients, quality)
        threads = make_threads(split, seed + si * 1000, persona_ids, jobs, gold)
        all_clients += clients
        all_quality.update(quality)
        write(out / f"jobs_{split}.jsonl", "".join(json.dumps(j, sort_keys=True) + "\n" for j in jobs), files)
        write(out / f"threads_{split}.json", dumps([{k: v for k, v in t.items() if k != "_gold"} for t in threads]), files)
        # ---- eval datasets (gold lives only here)
        jobmap = {j["job_id"]: j for j in jobs}
        retrieval = [{"id": g["job_id"], "persona": g["persona"], "class": g["class"],
                      "text": jobmap[g["job_id"]]["description"], "n_requirements": g["n_requirements"],
                      "requirements": naive_requirements(jobmap[g["job_id"]]), "requirements_oracle": g["asks"],
                      "gold": g["gold_evidence"], "gold_groups": g["gold_groups"]}
                     for g in gold if g["class"] in ("good_fit", "partial_fit", "out_of_scope", "lookalike")]
        decisions = [{"id": g["job_id"], "persona": g["persona"], "class": g["class"], "job": jobmap[g["job_id"]],
                      "gold": {"action": g["action"], "scam": g["scam"], "injection": g["injection"], "evasive": g["evasive"],
                               "price_band": g["price_band"], "client_quality": g["client_quality"]}} for g in gold]
        messages = [{"id": t["thread_id"], "persona": t["_gold"]["persona"], "messages": t["messages"],
                     "gold": {"intent": t["_gold"]["intent"], "evasive": t["_gold"]["evasive"]}} for t in threads]
        meta = {"synthetic": True, "is_toy": False, "generator_version": GENERATOR_VERSION, "seed": seed + si * 1000, "split": split,
                "note": "SYNTHETIC. Gold derived by rule from generator (see gigdata/synth.py docstring). Not real-world ground truth."}
        write(evals_dir / f"synth_retrieval_{split}.json", dumps({**meta, "corpora_root": "data/synthetic", "corpora": {p: f"personas/{p}/portfolio.json" for p in persona_ids}, "items": retrieval}), files)
        write(evals_dir / f"synth_decision_{split}.json", dumps({**meta, "items": decisions}), files)
        write(evals_dir / f"synth_messages_{split}.json", dumps({**meta, "items": messages}), files)
        summary[split] = {"jobs": len(jobs), "threads": len(threads), "by_class": {k: sum(g["class"] == k for g in gold) for k in CLASSES},
                          "retrieval_items": len(retrieval), "actions": {a: sum(g["action"] == a for g in gold) for a in ("bid", "watch", "skip")}}
    write(out / "clients.json", dumps(all_clients), files)
    write(out / "_ground_truth" / "client_quality.json", dumps(all_quality), files)
    manifest = {"generator_version": GENERATOR_VERSION, "seed": seed, "personas": persona_ids, "splits": list(splits),
                "summary": summary, "sha256": files}
    write(out / "MANIFEST.json", dumps(manifest), {})
    return manifest


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--evals", default="evals/datasets")
    a = ap.parse_args()
    m = build_all(Path(a.out), Path(a.evals), seed=a.seed)
    print(json.dumps(m["summary"], indent=2))
