# Signature extension — Semantic support grader for V8

## Problem
V8 (corrective RAG) decides which retrieved evidence *supports* each job requirement with a **strict lexical
grader** (`rag/variants/v8_corrective.supports`): keyword-overlap ratio ≥ threshold. Paraphrase defeats it —
"speech-to-text" vs a portfolio item about "Whisper transcription" shares few tokens, reads as unsupported,
so V8 drops the evidence and abstains. On the synthetic dev subset V8 scores **recall@5 0.156, coverage
0.250, nDCG 0.200** while abstaining on 75% of jobs (`docs/RESULTS.md`, `docs/AI_USAGE.md` #8).

## Design
`SemanticSupportGrader` (`rag/stages.py`) grades support by **embedding cosine** instead of token overlap. It
embeds the requirement and every candidate with the **same torch-free embedder the retriever uses** (Ollama
`nomic-embed-text` for a real semantic signal; the hash stand-in stays lexical), L2-normalised so dot product
is cosine, and keeps every candidate scoring ≥ a threshold. It implements the existing grader interface
(`supported_ids(requirement, items) -> set`), so it drops into V8 and the component factory
(`make_grader("semantic")`) with **no node or graph changes** — the point of the pluggable grader.

Hypothesis: semantic similarity recovers the paraphrased evidence the lexical grader misses, raising V8
recall/coverage **without losing abstention discipline** (V8 should still return nothing for jobs the persona
genuinely cannot support).

## Result (synthetic dev subset, same Ollama embedder, only the grader varied)

| V8 grader | Recall@5 | Coverage@5 | nDCG@10 | Abstain rate | file |
|---|---|---|---|---|---|
| lexical (baseline) | 0.156 | 0.250 | 0.200 | 0.75 | `rag_synth_dev_subset_v8_lexical.json` |
| **semantic (thr 0.60, chosen)** | **0.490** | **0.618** | **0.545** | **0.75** | `rag_synth_dev_subset_v8_semantic.json` |
| semantic (thr 0.55) | 0.640 | 0.861 | 0.660 | 0.50 | `rag_synth_dev_subset_v8_semantic_thr055.json` |

At the tuned threshold **0.60**, V8 recall **triples** (0.156 → 0.490) and coverage more than doubles, while
abstention stays at **0.75** — it still refuses every no-gold job. A lower threshold (0.55) buys more recall
(0.640) but starts returning evidence on no-gold jobs (abstain falls to 0.50), i.e. it becomes over-eager.
The threshold was swept on **dev only**; 0.60 is the operating point that keeps abstention intact.

## Limitations
- Synthetic **dev subset** (16 items, 4/persona) — small N; directional, not a population estimate. Holdout
  was deliberately not spent on this tuning.
- `nomic-embed-text` is queried without its task-prefix convention (kept consistent with the retriever's
  embedder); adding prefixes could shift the threshold.
- The reranker is still a lexical stand-in; only the **grader** is now a real component.
- Cost: the semantic grader embeds per requirement per corrective retry, so V8 p95 ≈ 20 s/job vs sub-second
  for the lexical grader — acceptable offline, not for interactive use without caching.

## Reproduce
```bash
py -m evals.runners.rag_eval --dataset evals/datasets/synth_retrieval_dev_subset.json \
  --embedder ollama:nomic-embed-text --grader lexical  --out evals/results/rag_synth_dev_subset_v8_lexical.json
```
```bash
py -m evals.runners.rag_eval --dataset evals/datasets/synth_retrieval_dev_subset.json \
  --embedder ollama:nomic-embed-text --grader semantic --out evals/results/rag_synth_dev_subset_v8_semantic.json
```
Requires `ollama serve` with `nomic-embed-text` pulled. Tests: `tests/unit/test_evals.py`
(`test_semantic_grader_mechanics`, `test_v8_uses_semantic_grader_when_configured`).
