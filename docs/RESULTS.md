# Results

**Sections 1–2 are synthetic** (machinery and variant ranking only); the **Real-data audit** section at the end is the one measurement on real posts. Every number is copied from a file in `evals/results/`.

## Retrieval and variant comparison (synthetic data only)

Every number below is copied from a file in `evals/results/`. All are **synthetic** dev/holdout results from a placeholder hashed embedder, a lexical reranker stand-in and a lexical V8 grader. They show the machinery works and how variants rank, not real-world accuracy. Holdout was run once, after the last code change. Rule recall and intent accuracy are inflated by shared template vocabulary (see `docs/AI_USAGE.md` #8).

## Retrieval, dev (`rag_synth_dev.json`)

| Variant | Recall@5 | Coverage@5 | MRR | nDCG@10 | Abstain rate | p95 ms |
|---|---|---|---|---|---|---|
| V0 naive dense | 0.432 | 0.696 | 0.701 | 0.616 | 0.00 | 0.2 |
| V1 decompose (naive reqs) | 0.363 | 0.621 | 0.630 | 0.582 | 0.00 | 0.2 |
| V1 decompose (oracle reqs) | 0.411 | 0.661 | 0.725 | 0.615 | 0.00 | 0.1 |
| V2 hybrid | 0.473 | 0.776 | 0.804 | 0.679 | 0.00 | 0.3 |
| V3 hybrid+rerank | 0.529 | 0.796 | 0.804 | 0.712 | 0.00 | 3.2 |
| V4 outcome-aware | 0.494 | 0.737 | 0.797 | 0.695 | 0.00 | 2.5 |
| V8 corrective | 0.139 | 0.221 | 0.415 | 0.194 | 0.75 | 5.3 |

## Retrieval, holdout (`rag_synth_holdout.json`)

| Variant | Recall@5 | Coverage@5 | MRR | nDCG@10 | Abstain rate | p95 ms |
|---|---|---|---|---|---|---|
| V0 naive dense | 0.390 | 0.644 | 0.669 | 0.610 | 0.00 | 0.1 |
| V1 decompose (naive reqs) | 0.361 | 0.628 | 0.661 | 0.586 | 0.00 | 0.2 |
| V1 decompose (oracle reqs) | 0.407 | 0.691 | 0.663 | 0.605 | 0.00 | 0.1 |
| V2 hybrid | 0.438 | 0.739 | 0.835 | 0.680 | 0.00 | 0.2 |
| V3 hybrid+rerank | 0.488 | 0.767 | 0.824 | 0.701 | 0.00 | 0.7 |
| V4 outcome-aware | 0.515 | 0.781 | 0.832 | 0.729 | 0.00 | 1.9 |
| V8 corrective | 0.160 | 0.262 | 0.534 | 0.228 | 0.67 | 4.0 |

Observations: hybrid, reranking and outcome-aware ranking each help over naive dense retrieval; decomposition with a naive sentence splitter does not (oracle requirements recover most of the gap); V8 abstains on most jobs because its lexical grader is too strict (needs an LLM/semantic grader).

Ablation: `ablation_synth_{dev,holdout}.json`. Decision baseline: `decision_rules_*`. Intent baseline: `intent_rules_*`.

## A/B experiments (Step 6 — synthetic dev, LLM held fixed)

Two controlled experiments. In both, the LLM is a deterministic scripted stand-in held fixed across arms, so each difference is attributable to the **one factor varied**. Runner: `evals/runners/ab_experiments.py` (`py -m evals.runners.ab_experiments --split dev`), 184 synthetic dev jobs. Because the LLM is fixed and the data is synthetic, these isolate the *pipeline's structural* effects, not LLM-quality interactions.

### A. Retrieval variant → bid decisions (`ab_retrieval_decisions_dev.json`)

Factor: the RAG variant feeding the Matcher. The support grader is held constant as the strict lexical check, so coverage reflects retrieval quality.

| Arm | Bid rate | Watch rate | Skip rate | Mean fit | Mean coverage |
|---|---|---|---|---|---|
| V0 naive dense | 0.038 | 0.168 | 0.793 | 0.224 | 0.224 |
| V2 hybrid | 0.060 | 0.207 | 0.734 | 0.265 | 0.265 |
| V3 hybrid+rerank | 0.043 | 0.212 | 0.745 | 0.257 | 0.257 |

Better retrieval propagates to decisions: V2 hybrid gives the highest requirement coverage (0.265 vs V0's 0.224), lifting the fit score so the agent **bids on ~58% more jobs** (0.060 vs 0.038) and skips fewer. The V2 ≳ V3 > V0 ranking matches the retrieval comparison above; the low absolute coverage is the strict lexical grader missing paraphrase (see `docs/AI_USAGE.md` #8), not the retrievers.

### B. Single-agent vs multi-agent (`ab_single_vs_multi_dev.json`)

Factor: graph topology. Multi-agent = the full bid graph (risk rules + matcher + verifier + critic + compliance); single-agent = one LLM call job→proposal with no guardrails. 33 of 184 jobs carry scam/injection signals (`agent/rules.py`). *Unsafe* = produced a proposal on a flagged job; *unsupported-claim* = a planted unsupported claim surviving in the produced proposal.

| Arm | Proposals produced | Unsafe-proposal rate | Unsupported-claim rate | Mean LLM calls |
|---|---|---|---|---|
| multi-agent (full graph) | 151 | 0.000 | 0.000 | 6.28 |
| single-agent (one-shot writer) | 184 | 1.000 | 1.000 | 1.00 |

The multi-agent graph skips all 33 flagged jobs and the verifier strips the planted claim from every produced proposal, at ~6.3 LLM calls/job. The single-agent writer is **6× cheaper** (1 call) but ships a proposal on every scam job and keeps every unsupported claim. **When does a single agent win?** Only on cost, and only for already-clean jobs — it has no mechanism to detect scams, verify claims or enforce policy, so the multi-agent guardrails are what make the system safe to run unattended. Tests of these guardrails: `tests/unit/test_bid_graph.py`.

## Real-data audit of the rule detector (NOT synthetic)

The only non-circular check in this repo. A human (the project owner) labelled **60 real Upwork posts** (`upwork_50k_2024`: 30 rule-flagged + 30 unflagged, shown blind to the rule flags) as scam / injection / legit, then scored them against `agent/rules.py`.

| Metric | Value | detail |
|---|---|---|
| Flag precision | **0.43** | 13/30 flagged posts were bad (scam/injection) by human judgment |
| Miss rate among unflagged | **0.30** | 9/30 posts the rules left clean were bad |
| Estimated recall (stratified, full set) | **~0.02** | over 871 flagged + 52,083 unflagged real posts |

Source: `evals/results/audit_real_upwork_50k_2024.json`. The labelled sample (`data/processed/audit_sample.csv`) stays git-ignored; the Kaggle licence is unverified.

**Takeaway:** the rules look strong on synthetic data (shared template vocabulary — see `docs/AI_USAGE.md` #8) but are **weak on real posts**: low precision and near-zero recall. Most false positives are `off_platform_contact` (13) and `unpaid_work` (4) firing on legitimate posts — including posts whose text says "no contact outside Upwork" or offers a "free trial". **Caveats:** single auditor, one source and time window (Feb 2024 scrape), n=60 (precision 95% CI ≈ ±0.18), and the recall figure extrapolates a 30-sample miss rate across 52k posts, so it is order-of-magnitude only.
