"""Celery wrapper (Redis broker). Thin on purpose: all logic is in scout.py so it is unit-tested without Redis.

Run:  celery -A worker.tasks worker -l info      and      celery -A worker.tasks beat -l info
NOTE: untested here (no Redis in the dev sandbox); verify with docker compose.
"""
import os

from celery import Celery

app = Celery("gigbid", broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
# live mode uses a conservative interval; justify it in docs/RUNBOOK.md
app.conf.beat_schedule = {
    "scout-all-users": {"task": "worker.tasks.scout_all", "schedule": float(os.environ.get("SCOUT_INTERVAL_S", 14400))},
}


@app.task(name="worker.tasks.scout_all")
def scout_all():
    raise NotImplementedError("load users + saved searches, build the marketplace client, call scout_once, enqueue run_bid")


@app.task(name="worker.tasks.run_bid", acks_late=True)
def run_bid(user_id: str, job_id: str):
    raise NotImplementedError("POST to API /runs (idempotent per user+job) or call the graph directly")
