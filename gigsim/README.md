# GigSim — self-built marketplace simulator

**This is not the instructor's GigSim.** The official GigSim service was not included in the
`GigBid_Student_Starter_Kit_v0.1` (the kit only *references* "the provided GigSim service" and sets
`GIGSIM_BASE_URL=http://localhost:8081`). This package is a faithful-enough local stand-in built to that
convention so GigBid can run, demo and be tested end-to-end over HTTP. If the real service is ever supplied,
point the adapter at its README instead — no node or graph changes, only `mcp_servers/marketplace/adapters/gigsim.py`.

What it adds over the in-process `SyntheticBackend`: a real HTTP surface, bearer auth, a published rate
limit, Connects accounting, and **deterministic simulated client replies**.

## Run

```bash
py -m gigsim            # http://localhost:8081, split=dev, dev token
```

Environment (starter-kit-compatible names; `GIGSIM_URL` / `GIGSIM_API_KEY` are read as fallbacks):

| Var | Default | Meaning |
|---|---|---|
| `GIGSIM_API_TOKEN` | `dev-local-token` | bearer token clients must present |
| `GIGSIM_PORT` | `8081` | listen port |
| `GIGSIM_DATA_DIR` | `data/synthetic` | synthetic data root |
| `GIGSIM_SPLIT` | `dev` | `dev` or `holdout` |
| `GIGSIM_CONNECTS` | `200` | starting Connects balance |
| `GIGSIM_RATE_PER_MIN` | `20` | requests/min per token |

## Auth & rate limit

- Every endpoint except `GET /health` requires `Authorization: Bearer <GIGSIM_API_TOKEN>`; otherwise `401`.
- Each token gets a token bucket of **20 requests/minute** (matches the starter-kit
  `marketplace.max_requests_per_minute`). On exhaustion: `429` with a `Retry-After` header, which the
  adapter already treats as retryable with back-off. The client-side `RateLimiter` in
  `mcp_servers/marketplace/infra.py` is set to the same ceiling so well-behaved clients never hit `429`.

## Endpoints

| Method & path | Returns |
|---|---|
| `GET /health` | `{status, jobs, note}` — unauthenticated |
| `GET /jobs?q=&limit=` | list of job objects whose title/description contains `q` |
| `GET /jobs/{job_id}` | one job object (`404` if unknown) |
| `GET /clients/{client_id}` | client-history object (`404` if unknown) |
| `GET /me/connects` | `{"balance": int}` |
| `GET /threads/{thread_id}/messages` | list of `{from, body}` messages |
| `POST /proposals` | body `{job_id, cover_letter, amount, answers}` → `{proposal_id, job_id, amount, status:"draft", connects_spent, connects_balance}`; spends the job's `connects_cost` |
| `POST /proposals/{proposal_id}/submit` | flips status to `"submitted"` (no extra Connects) |
| `POST /threads/{thread_id}/messages` | body `{body}` → appends the freelancer message, generates a client reply, returns `{message_id, thread_id, body, client_reply}` |

Job / client / message objects have the same shape as `data/synthetic` (see `docs/DATA_CARD.md`).

## Simulated client replies

`POST /threads/{id}/messages` appends the freelancer's line, then a client reply from
`gigsim/client_sim.py`. The reply is **deterministic** — template choice is seeded by
`(thread_id, reply_index)`, so a conversation replays identically across runs and restarts, with no LLM
call and no cost. Replies progress through clarify → commercials → schedule-a-call → wind-down stages and
are benign by design; prompt-injection handling is exercised by separate fixtures, not injected here.

## Safety

State is in-memory and reset on restart. `POST /proposals` and `.../submit` and message sends are writes
inside the simulator only — the agent still routes every real external action through the human-approval
interrupt before it ever calls them. Nothing here talks to Upwork or any live marketplace.
