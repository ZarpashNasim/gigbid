# Runbook

Operational notes for running, deploying and recovering GigBid. Environment: Windows 11, Python 3.14
(use `py`), no `make` wrapper — run the Makefile commands directly. If a dependency breaks on 3.14, use
Python 3.12 (the Docker images already pin 3.12).

## 1. Local, no Docker

Each in its own terminal, from the repo root:

```bash
ollama serve
```

```bash
ollama pull nomic-embed-text
```

```bash
py -m gigsim
```

```bash
py -m uvicorn --factory apps.api.entrypoint:build_app --host 127.0.0.1 --port 8000
```

```bash
cd apps/web && npm install && npm run dev
```

Copy `.env.example` to `.env` first and fill the LLM key for your profile (`GROQ_API_KEY` or
`OPENROUTER_API_KEY`). Never commit `.env`. The API reads `MARKETPLACE_MODE` (`gigsim` | `synthetic`),
`GIGSIM_BASE_URL`, `EMBEDDER`, `RAG_VARIANT`, `API_TOKENS` (a JSON `{"token": "user_id"}` map).

Offline, no keys, no GigSim: set `MARKETPLACE_MODE=synthetic` to serve `data/synthetic` in-process (this is
the stand-in, **not** GigSim — no rate limits or simulated client replies).

## 2. Docker (full stack)

```bash
docker compose -f infra/docker-compose.yml up --build
```

Then once, into the ollama service: `docker compose -f infra/docker-compose.yml exec ollama ollama pull nomic-embed-text`.
Services: postgres, redis, ollama, gigsim (:8081), api (:8000), worker (celery), web (:3000). The compose
file is a working skeleton — it needs your `.env` and the pull above; the worker tasks are still stubs
(`worker/tasks.py`).

## 3. Rate limits

- **GigSim** publishes 20 requests/minute per token and returns `429` + `Retry-After` past that; the
  Marketplace MCP server's client-side `RateLimiter` is set to the same ceiling so clients stay under it.
- **Groq free tier** limits tokens-per-minute. `agent/llm.py` paces 429s (reads "try again in Ns", sleeps,
  retries) instead of failing. Heavy LLM eval runs can still exhaust it — prefer a local Ollama chat model
  for large retrieval/grader runs (see `docs/AI_USAGE.md` #12).

## 4. Recovery & degraded mode

- **Resume after crash:** the bid/conversation graphs checkpoint to Postgres (`CHECKPOINT_URL`); an
  interrupted run resumes from its last node. Writes are idempotent (`mcp_servers/marketplace/infra.py`
  sqlite idempotency store) so a retry never submits a proposal or spends Connects twice.
- **Marketplace down:** adapter retries with back-off, then raises `MarketplaceUnavailable`; the UI shows
  degraded mode and work is queued rather than lost.
- **Audit:** every marketplace tool call is appended to an append-only JSONL audit log (user, tool, args,
  result, trace id).

## 5. Deploy to a public URL (reviewer access)

**Fastest path:** a `render.yaml` Blueprint at the repo root wires the API + web UI + Postgres for a
near one-click deploy on Render (New → Blueprint → pick the repo). It deploys in `MARKETPLACE_MODE=synthetic`
for reliability; set the `GROQ_API_KEY` secret and, after the API gets its URL, set `API_URL` on the web
service (the Next server proxies `/api/*` to it). See the comments in `render.yaml`.

Manual path, any host (needs your hosting account — Claude does not deploy on your behalf):
1. Build and push the `api` and `web` images to your host (Render/Fly/Railway/a VPS with the compose file).
2. Provision managed Postgres + Redis, set `CHECKPOINT_URL` / `REDIS_URL`, and the LLM key.
3. Run GigSim (or point `GIGSIM_BASE_URL` at the instructor's service if provided).
4. Set `API_URL` on the web service to the public API URL (the Next server proxies `/api/*` to it).
5. Open the web URL, sign in with a token from `API_TOKENS`, run one job end-to-end to the approval screen,
   and confirm the reviewer can reach it. Record the URL in the README.

## 6. Evaluation & the holdout rule

Dev evals: `make eval-synth` (or the `python -m evals.runners.*` commands). **Holdout is run once** for final
reporting and never tuned against (`make eval-holdout`; A/B via `py -m evals.runners.ab_experiments --split
holdout`). Every reported number must trace to a file in `evals/results/`.
