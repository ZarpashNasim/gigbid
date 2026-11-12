# Viva prep

Likely examiner questions with honest, repo-grounded answers. Know where every claim lives in the code.

**Q. Walk me through one job end-to-end.**
`intake` loads the job from the marketplace port → `analyst`, `risk`, `matcher` run in parallel (LangGraph
`Send`) → `decide` bids or skips → `pricing` → `writer` drafts → `verifier` strips unsupported claims →
`critic` (≤2 loops) → `compliance` → **`interrupt()` for human approval** → `submit`. State is a typed
`BidState`; every hand-off is a Pydantic model (`agent/graphs/bid_graph.py`, `agent/handoffs.py`).

**Q. Where is the human actually in control?**
`approval` calls LangGraph `interrupt()`; nothing is submitted or sent and no Connects are spent before the
human approves. Writes are idempotent, so an approved retry never double-submits. Tests:
`test_happy_path_interrupts_then_submits_once`, `test_reject_sends_nothing`.

**Q. Why multi-agent instead of one LLM call?**
Experiment B (`evals/results/ab_single_vs_multi_*`): the single-agent writer ships a proposal on 100% of
scam/injection jobs and keeps every unsupported claim; the multi-agent graph blocks them (0.00 unsafe) via
deterministic risk rules, the claim verifier and the compliance guard — at ~6× the LLM calls. So multi-agent
buys safety; single-agent only wins on cost for already-clean jobs.

**Q. Did better retrieval change the agent's behaviour, or just the metrics?**
Experiment A: it changed decisions. V2 hybrid's higher requirement coverage raised the fit score enough to
bid on ~58% more jobs than V0, and the ranking held on holdout.

**Q. Your rules look great on synthetic data — are they actually good?**
No. The only non-circular check is a human audit of 60 real Upwork posts: precision 0.43, near-zero recall
(`docs/RESULTS.md`). The synthetic scores are inflated by shared template vocabulary — disclosed in
`docs/AI_USAGE.md` #8. Most false positives are legitimate posts that merely mention "no off-platform
contact" or a "free trial".

**Q. Is GigSim the instructor's simulator?**
No — the starter kit did not include it (only `GIGSIM_BASE_URL=:8081`, 20/min). `gigsim/` is a self-built
stand-in with bearer auth, the rate limit, Connects accounting and deterministic client replies; swapping in
the real service touches only one adapter file. Disclosed in `docs/AI_USAGE.md` #11.

**Q. How do you know your numbers are real?**
Every number traces to a file in `evals/results/`. One Groq run was contaminated by rate-limit fallbacks and
**deleted rather than reported** (`docs/AI_USAGE.md` #12). Holdout was run once and never tuned against.

**Q. Prompt-injection resistance?**
Untrusted text is wrapped in delimiters and prompts are told never to follow instructions inside it
(`agent/config.wrap_untrusted`); deterministic rules flag injection patterns the LLM cannot remove; a scam
job is skipped before any drafting (`test_scam_is_skipped_without_drafting`,
`test_legit_llm_prompt_job_is_not_flagged_but_real_injection_is`).

**Q. Biggest weaknesses?**
Synthetic evals; self-built GigSim; the V8/strict-lexical grader over-abstains; single-auditor real-data
study (n=60); worker tasks are stubs; no live public deployment yet. All listed in `README.md` and
`docs/AI_USAGE.md`.

**Q. A new marketplace policy lands tomorrow — what changes?**
A config line, not code: the compliance guard reads `policy.extra_rules` and thresholds from
`agent/config.yaml` (`test_policy_change_is_config_only`).
