# GigBid — R&D Report

## 1. Problem & system overview

GigBid is a multi-agent copilot that helps a freelancer work a job marketplace: it discovers and triages
jobs, assesses risk, matches portfolio evidence to each requirement, prices the work, drafts a proposal and
client replies, and **stops at a human-approval gate before any external action**. No proposal is submitted,
no message is sent, and no Connects are spent without an explicit human decision.

The system is two LangGraph state machines over a set of typed Pydantic hand-offs:

- **Bid graph** (`agent/graphs/bid_graph.py`): `intake → [analyst ‖ risk ‖ matcher] → decide →
  pricing → writer → verifier → critic (≤2 loops) → compliance → approval (interrupt) → submit`. The three
  analysis nodes run in parallel (LangGraph `Send`).
- **Conversation graph** (`agent/graphs/conversation_graph.py`): `load → classify → draft → compliance →
  approval → send`, where a scam signal ends the thread before any reply is drafted.

Around these sit a single **marketplace port** with swappable backends, read/write **MCP tool servers** with
idempotency and audit, a **RAG** retrieval stack, deterministic **guardrails** (scam rules, claim verifier,
compliance guard), a FastAPI backend with SSE streaming, and a Next.js UI. Architecture detail: `README.md`.

## 2. Tool design & marketplace port

Every external capability is behind one interface, `MarketplacePort` (`agent/marketplace_port.py`), with
three adapters: **GigSim** (HTTP simulator), **synthetic** (in-process, offline), and **in-memory** (tests).
Switching marketplaces is a config change — no node is touched — which is the single most important design
decision: it let the whole system run and be tested offline while the marketplace stayed pluggable. GigSim
itself is **self-built** (`gigsim/README.md`) because the instructor's service was not included in the
starter kit; it is clearly labelled as a stand-in everywhere.

The Marketplace MCP server (`mcp_servers/marketplace/server.py`) was the design that gave the most reliable
tool selection and arguments, for three reasons:

1. **Typed, constrained I/O.** Every tool has Pydantic-validated inputs (length/range bounds) and a declared
   output schema, so malformed arguments are rejected before any side effect.
2. **Correct read/write annotations + `dry_run` previews.** Writes default to `dry_run=True`, returning
   exactly what *would* be sent and its Connects cost; the destructive hint and idempotency hint are set per
   tool. This made the agent's "preview then confirm" behaviour the default rather than the exception.
3. **Idempotency keys + append-only audit.** A retry with the same key never submits a proposal or spends
   Connects twice (`mcp_servers/marketplace/infra.py`), and every call is logged with user, tool, args,
   result and trace id. Tests: `mcp_servers/marketplace/tests/test_marketplace_server.py`.

## 3. RAG variants & retrieval

Variants V0 (naive dense) → V1 (decompose) → V2 (hybrid BM25+dense RRF) → V3 (hybrid+rerank) → V4
(outcome-aware) → V8 (corrective), over a pluggable embedder (hash stand-in or local Ollama
`nomic-embed-text`). Development results (`evals/results/rag_synth_dev.json`, `docs/RESULTS.md`):

| Variant | Recall@5 | Coverage@5 | nDCG@10 |
|---|---|---|---|
| V0 naive dense | 0.432 | 0.696 | 0.616 |
| V2 hybrid | 0.473 | 0.776 | 0.679 |
| V3 hybrid+rerank | **0.529** | **0.796** | **0.712** |
| V4 outcome-aware | 0.494 | 0.737 | 0.695 |
| V8 corrective | 0.139 | 0.221 | 0.200 |

**Which variant improved retrieval?** Hybrid, reranking and outcome-aware ranking each beat naive dense;
V3 (hybrid + rerank) is the best single retriever on the dev set, and the ranking holds on holdout
(`rag_synth_holdout.json`). Two honest caveats: (a) V8's recall looks terrible (0.139) because its *lexical*
support grader is too strict and abstains on ~75% of jobs — addressed by the signature extension (§8); and
(b) these numbers use the hash **stand-in** embedder. Swapping in the real Ollama `nomic-embed-text` embedder
lifts dense retrieval sharply (`rag_synth_dev_subset_{baseline,ollama}.json`): V0 recall 0.388 → **0.616** and
nDCG 0.623 → **0.806** on the dev subset, with 0 LLM fallbacks. Ablation of decompose/hybrid/rerank:
`ablation_synth_*`.

## 4. Experiments (A/B)

Two controlled experiments (`evals/runners/ab_experiments.py`) on the 184 synthetic dev jobs, with the LLM
**held fixed** (a deterministic scripted stand-in) so each difference is attributable to the one factor
varied. Because the LLM is fixed and the data synthetic, these isolate the *pipeline's structure*, not
LLM-quality interactions.

**A. Retrieval variant → bid decisions** (`ab_retrieval_decisions_dev.json`). Grader held constant as the
strict lexical check, so coverage reflects retrieval quality:

| Arm | Bid rate | Skip rate | Mean fit | Mean coverage |
|---|---|---|---|---|
| V0 naive dense | 0.038 | 0.793 | 0.224 | 0.224 |
| V2 hybrid | **0.060** | 0.734 | **0.265** | **0.265** |
| V3 hybrid+rerank | 0.043 | 0.745 | 0.257 | 0.257 |

Better retrieval propagates to *decisions*: V2 hybrid's higher requirement coverage raises the fit score
enough to make the agent **bid on ~58% more jobs** than V0 (0.060 vs 0.038) and skip fewer. The effect holds
out of sample (`ab_retrieval_decisions_holdout.json`: V2 bid 0.087 vs V0 0.054).

**B. Single-agent vs multi-agent** (`ab_single_vs_multi_dev.json`), 33 of 184 jobs carrying scam/injection
signals:

| Arm | Proposals produced | Unsafe-proposal rate | Unsupported-claim rate | Mean LLM calls |
|---|---|---|---|---|
| multi-agent (full graph) | 151 | **0.000** | **0.000** | 6.28 |
| single-agent (one-shot writer) | 184 | 1.000 | 1.000 | 1.00 |

The multi-agent graph skips every scam/injection job and strips every unsupported claim; the single-agent
writer is **6× cheaper** but ships a proposal on every flagged job and keeps every unsupported claim. Same
conclusion on holdout (34 risky jobs).

**Did better retrieval improve simulated client replies?** No — and the honest reason is a limitation of my
own simulator: GigSim's client replies are template-based and *not conditioned on proposal content*
(`gigsim/client_sim.py`), so they do not vary with retrieval quality. A content-aware (e.g. LLM-driven)
simulator would be needed to measure that link.

**When does a single agent beat a multi-agent graph?** Only on cost, and only for already-clean jobs: the
single agent has no mechanism to detect scams, verify claims or enforce policy, so the multi-agent
guardrails are precisely what make the system safe to run with a human only at the final gate.

## 5. Claim verification, risk & compliance

Three deterministic layers back the LLM so safety does not depend on a model behaving:

- **Risk rules** (`agent/rules.py`): keyword/intent detectors for scams and prompt injection. The LLM Risk
  Assessor may *add* flags but can never remove a rule-derived one.
- **Claim verifier** (`agent/nodes/writing.py`): splits the draft into claims and removes any marked
  unsupported *before* the Critic sees it; an invented evidence id is ignored.
- **Compliance guard** (`agent/nodes/compliance.py`): policy-pack enforcement (off-platform contact,
  guarantees, length) driven from config, so a policy change is a one-line config edit, not code.

**Prompt-injection and human-approval testing** (`tests/unit/test_bid_graph.py`): a scam/injection job is
skipped before any drafting (`test_scam_is_skipped_without_drafting`); the approval gate always pauses and
submits exactly once (`test_happy_path_interrupts_then_submits_once`); reject/edit send nothing
(`test_reject_sends_nothing`, `test_edit_is_recompliance_checked`); and
`test_legit_llm_prompt_job_is_not_flagged_but_real_injection_is` shows the detector distinguishes a legitimate
"write me a system prompt" job from an actual injection.

**The honest headline (real data):** the only non-circular evaluation is a human audit of **60 real Upwork
posts** (`evals/results/audit_real_upwork_50k_2024.json`): flag **precision 0.43**, miss rate 0.30 among
unflagged, and estimated **recall ~0.02**. The rules look strong on synthetic data but are weak on real
posts — most false positives are legitimate posts that merely mention "no off-platform contact" (13) or a
"free trial" (4). The synthetic scores are inflated by shared template vocabulary (disclosed in
`docs/AI_USAGE.md` #8); holdout does not remove this because it uses the same templates.

## 6. Failure analysis

Concrete failures caught and fixed during development (full log in `docs/AI_USAGE.md`):

1. **Approvals landed in `dead_letter`.** The dead-letter wrapper caught LangGraph's `interrupt` signal.
   Diagnosed by tracing a paused approval; fixed by re-raising `GraphBubbleUp`.
2. **Non-deterministic retrieval.** The placeholder embedder used Python's per-process `hash()`; fixed with
   a stable crc32 so results reproduce.
3. **Matcher over-optimism.** The grader first counted a requirement as covered if retrieval returned *any*
   evidence, so every job looked like a fit. Caught by a degenerate rules-only baseline; replaced with a
   support grader plus a strict lexical fallback that ignores invented ids.
4. **Windows byte-determinism.** `path.write_text()` translated `\n→\r\n` on Windows while the manifest
   hashed UTF-8 bytes, so the hash test passed on Linux and failed on Windows; fixed with `write_bytes`.
5. **Contaminated eval, deleted not reported.** A Groq free-tier "all-real" run fell back to lexical graders
   on 48 calls due to the token-per-minute limit, so its numbers were mostly lexical; the file was deleted
   rather than cited, and the clean result path (local Ollama) was used instead.

## 7. Deployment

Containerised with `infra/docker/Dockerfile.{api,web}` and two compose files: `infra/docker-compose.yml`
(full stack: API + web + GigSim + Postgres + Redis + Ollama) and `infra/docker-compose.demo.yml` (a minimal,
reliable API + GigSim demo). A `render.yaml` Blueprint deploys the API + web to Render; the deployed API runs
in `MARKETPLACE_MODE=synthetic` for reliability, and the Next.js proxy target (`API_URL`) is baked at build
time. Operational notes, rate limits, recovery and the deploy procedure: `docs/RUNBOOK.md`.

- API (health + Swagger): `https://gigbid-api-f0mo.onrender.com/docs`
- Web UI: `https://gigbid-web-1aym.onrender.com/`
- **Demo video:** `https://drive.google.com/file/d/1mxSYZ8749E-FXlobFYA2ZzMVJRfBy0Ot/view?usp=sharing`
- End-to-end check performed: signed in with a token, analysed a clean job (`syn-dev-ai_engineer-002`) to the
  approval screen, and confirmed a scam job (`syn-dev-ai_engineer-034`, upfront-fee) is skipped before any
  proposal is drafted. Nothing is sent without approval.

## 8. Signature extension — semantic support grader

V8's corrective loop decided requirement support with a **strict lexical** grader (keyword overlap), which
misses paraphrase and so abstained on ~75% of jobs (recall 0.156). The extension `SemanticSupportGrader`
(`rag/stages.py`) grades support by **embedding cosine** over the same torch-free Ollama embedder, keeping
every candidate above a dev-tuned threshold. It implements the existing grader interface, so it drops into V8
and the component factory with no graph change. Result on the dev subset (same embedder, only the grader
varied; `rag_synth_dev_subset_v8_{lexical,semantic}.json`):

| V8 grader | Recall@5 | Coverage@5 | nDCG@10 | Abstain rate |
|---|---|---|---|---|
| lexical (baseline) | 0.156 | 0.250 | 0.200 | 0.75 |
| **semantic (thr 0.60)** | **0.490** | **0.618** | **0.545** | **0.75** |

At the tuned threshold 0.60, V8 recall **triples** while abstention discipline is fully preserved (it still
refuses every no-gold job). A lower threshold (0.55) buys more recall (0.640) but starts returning evidence
on no-gold jobs (abstain 0.50) — the classic recall/precision trade-off. Threshold tuned on **dev only**;
holdout was not spent on it. Full design and limitations: `docs/EXTENSION.md`.

## 9. Limitations & honesty

- Evaluations are **synthetic** except the 60-post real-data rule audit, which is the only non-circular check
  and shows the rules are weak on real posts.
- **GigSim is self-built**, not the instructor's service; its client replies are not content-aware.
- The reranker and (baseline) grader are named **stand-ins**; only the dense embedder and the semantic grader
  are real components.
- The rule/intent synthetic scores are inflated by shared template vocabulary (disclosed).
- Single-auditor real-data study (n=60, precision 95% CI ≈ ±0.18; recall is order-of-magnitude only).
- Worker tasks are stubs; the full compose stack is a skeleton; the public deploy runs in synthetic mode.
- Full AI-usage and error disclosure: `docs/AI_USAGE.md`.
