# GigBid

A multi-agent copilot that helps a freelancer triage marketplace jobs, assess risk, match portfolio
evidence, price, and draft proposals and client replies — **stopping at a human approval gate before any
external action**. Built for AI-4016 (Agentic AI, Assignment II).

## Live demo

- **Web UI:** https://gigbid-web-1aym.onrender.com/  (login token provided privately in the submission comment; then try job `syn-dev-ai_engineer-002`, or `syn-dev-ai_engineer-034` to see a scam skipped)
- **API (health + Swagger):** https://gigbid-api-f0mo.onrender.com/docs
- **Demo video:** https://drive.google.com/file/d/1mxSYZ8749E-FXlobFYA2ZzMVJRfBy0Ot/view?usp=sharing

> Deployed on Render free tier in `MARKETPLACE_MODE=synthetic`; the first request may take ~50s to wake the service.

> **Honesty banner.** Evaluation data is **synthetic** except the real-data rule audit (`docs/RESULTS.md`).
> The marketplace backend is a **self-built GigSim simulator** (`gigsim/`), not the instructor's service,
> which was not provided. Some components run as named stand-ins (strict-lexical grader, lexical reranker).
> Every reported number traces to a file in `evals/results/`. See `docs/AI_USAGE.md` for what went wrong and
> what is a substitute.

## What it does

- **Bid graph** (`agent/graphs/bid_graph.py`): intake → parallel Analyst / Risk / Matcher → bid-or-skip
  decision → pricing → writer → claim verifier → bounded critic loop → compliance guard →
  **human approval (LangGraph `interrupt`)** → submit. Typed Pydantic hand-offs between every step.
- **Conversation graph** (`agent/graphs/conversation_graph.py`): classify a client message (scam signals
  end the thread) → draft reply → compliance → approval → send.
- **Guardrails:** deterministic scam/injection rules (`agent/rules.py`) the LLM can extend but not weaken; a
  claim verifier that strips unsupported claims; a policy-pack compliance guard; per-user rate limiting,
  idempotent writes and an append-only audit log (`mcp_servers/marketplace/`).
- **RAG** (`rag/`): V0 naive dense → V2 hybrid (BM25+dense RRF) → V3 rerank → V4 outcome-aware → V8
  corrective, over a pluggable embedder (hash stand-in or local Ollama `nomic-embed-text`).
- **GigSim** (`gigsim/`): a local FastAPI marketplace simulator with bearer auth, a 20/min rate limit,
  Connects accounting and deterministic simulated client replies.

## Quick start

See **`docs/RUNBOOK.md`** for local (no-Docker) and full Docker bring-up. Shortest offline path:

```bash
py -m gigsim
```

```bash
py -m uvicorn --factory apps.api.entrypoint:build_app --host 127.0.0.1 --port 8000
```

Set `MARKETPLACE_MODE=synthetic` to run fully offline with no LLM key or GigSim. Tests: `py -m pytest -q`.

## Repository map

| Path | What |
|---|---|
| `agent/` | graph state, nodes, prompts, model config, memory, deterministic rules |
| `rag/` | portfolio ingestion, retrieval variants, claim support |
| `mcp_servers/` | Marketplace + Portfolio MCP servers, adapters (GigSim / synthetic / in-memory), infra |
| `gigsim/` | self-built marketplace simulator (stand-in) |
| `apps/api`, `apps/web` | FastAPI backend (+ streaming/approval) and Next.js UI |
| `worker/` | Celery scout scheduling (tasks are stubs) |
| `gigdata/` | deterministic synthetic data generator, data card, real-data loader + audit |
| `evals/` | retrieval eval, ablation, decision/intent baselines, A/B experiments, results |
| `infra/` | Dockerfiles + docker-compose |
| `docs/` | architecture, results, data card, runbook, AI-usage, report, viva |

## Results (summary — all trace to `evals/results/`)

- **Retrieval (synthetic dev):** hybrid, reranking and outcome-aware ranking each beat naive dense; the real
  Ollama embedder lifts dense recall/nDCG sharply over the hash stand-in.
- **A/B — retrieval → decisions:** V2 hybrid's higher requirement coverage makes the agent bid on ~58% more
  jobs than V0 (holds on holdout).
- **A/B — single vs multi-agent:** the multi-agent graph blocks 100% of scam/injection jobs and strips every
  unsupported claim; the single-agent writer is 6× cheaper but unsafe on every flagged job.
- **Extension — semantic support grader:** replacing V8's lexical grader with an embedding-cosine grader
  (`rag/stages.SemanticSupportGrader`) triples V8 recall (0.156→0.490) at unchanged abstention
  (`docs/EXTENSION.md`).
- **Real-data audit:** the rule detector looks strong on synthetic data but is **weak on 60 real Upwork
  posts** (precision 0.43, near-zero recall) — the only non-circular check. Full detail in `docs/RESULTS.md`.

## Safety

Job posts and client messages are untrusted input; embedded instructions are never followed. No proposal,
message or Connects spend happens without explicit human approval. No Upwork scraping. Secrets and real
client data stay out of Git.

## Status / not done

Worker tasks are stubs; the compose file is an untested skeleton; public deployment is the operator's step
(`docs/RUNBOOK.md` §5). A live-Upwork adapter is future work. The signature extension (semantic support
grader) is done — see `docs/EXTENSION.md`.
