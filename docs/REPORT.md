# GigBid — R&D Report (skeleton)

Fill the **TODO** blocks with your own narrative. Every number cited here must come from a file in
`evals/results/`; the pointers are pre-filled. Keep the honesty caveats (synthetic data, self-built GigSim,
stand-in components) — they are part of the grade.

## 1. Problem & system overview
TODO: one paragraph on what GigBid does and the human-in-the-loop principle. Architecture diagram:
bid graph + conversation graph + marketplace port + MCP servers + RAG + approval gate
(`agent/graphs/`, `README.md`).

## 2. Tool design & marketplace port
- Single `MarketplacePort` interface with GigSim / synthetic / in-memory adapters; switching backends is a
  config change (`agent/marketplace_port.py`, `mcp_servers/marketplace/adapters/`).
- Marketplace MCP server: Pydantic-typed I/O, correct read/write annotations, idempotency keys, `dry_run`
  previews, per-user rate limiting, append-only audit (`mcp_servers/marketplace/server.py`).
- GigSim is **self-built** (`gigsim/README.md`) because the instructor's service was not provided.
TODO: *Which tool design gave the most accurate tool selection and arguments?* Discuss the typed-schema +
dry_run approach and the idempotency/annotation choices.

## 3. RAG variants & retrieval
- Variants V0–V4, V8 with a pluggable embedder (hash stand-in vs local Ollama `nomic-embed-text`).
- Dev & holdout retrieval: `docs/RESULTS.md`, files `rag_synth_dev.json` / `rag_synth_holdout.json`;
  embedder swap `rag_synth_dev_subset_{baseline,ollama}.json`; ablation `ablation_synth_*`.
TODO: *Which RAG variant improved evidence retrieval on your dev set?* Cite the table; note the V8 lexical
grader's over-abstention and the embedder gain.

## 4. Experiments (A/B)
Runner `evals/runners/ab_experiments.py` (LLM held fixed; synthetic data — isolates pipeline structure).
- **A. Retrieval → bid decisions** (`ab_retrieval_decisions_{dev,holdout}.json`): V2 hybrid lifts coverage
  and bid rate over V0/V3; the effect holds on holdout.
- **B. Single-agent vs multi-agent** (`ab_single_vs_multi_{dev,holdout}.json`): multi-agent blocks 100% of
  scam/injection jobs and strips unsupported claims (unsafe 0.00) vs single-agent (unsafe 1.00) at 6× the
  LLM calls.
TODO: *Did better retrieval improve simulated client replies?* — discuss honestly: GigSim's replies are
template-based and not conditioned on proposal content, so they do not vary with retrieval; state this as a
limitation of the simulator. *When did a single agent perform better than a multi-agent graph?* — only on
cost for already-clean jobs.

## 5. Claim verification, risk & compliance
- Deterministic scam/injection rules (`agent/rules.py`); claim verifier removes unsupported claims before
  the critic; policy-pack compliance guard. Tests: `tests/unit/test_bid_graph.py`.
- **Real-data audit** (the only non-circular check): 60 real Upwork posts, precision 0.43, near-zero recall
  (`evals/results/audit_real_upwork_50k_2024.json`, `docs/RESULTS.md`).
TODO: *How did you test prompt-injection resistance and human approval?* Cite the scam-skip and
approval/interrupt tests, and the disclosed circularity (`docs/AI_USAGE.md` #8).

## 6. Failure analysis
TODO: *What failed, how did you diagnose it, and what changed after the fix?* Draw directly from
`docs/AI_USAGE.md` (interrupt swallowed by dead-letter; non-deterministic hash; V8 counter; Matcher
optimism; Windows byte-determinism; contaminated Groq eval deleted).

## 7. Deployment
Docker compose + Dockerfiles (`infra/`), runbook (`docs/RUNBOOK.md`). Public deployment + reviewer access:
TODO — record the URL and the end-to-end check you ran.

## 8. Signature extension — semantic support grader
Done: `SemanticSupportGrader` (`rag/stages.py`) replaces V8's strict-lexical grader with embedding cosine,
tripling V8 recall (0.156→0.490) at unchanged abstention on the dev subset. Design, before/after, threshold
tuning and limitations: `docs/EXTENSION.md`; numbers trace to `rag_synth_dev_subset_v8_{lexical,semantic}.json`.
TODO: add your own commentary / any further ablation.

## 9. Limitations & honesty
Synthetic evals; self-built GigSim; stand-in grader/reranker; single-auditor real-data study; worker stubs.
Full disclosure: `docs/AI_USAGE.md`.
