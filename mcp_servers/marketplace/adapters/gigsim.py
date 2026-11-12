"""GigSim adapter.  !! ENDPOINTS BELOW ARE GUESSES !! Fix paths/fields against the real GigSim README
from the Classroom starter kit; nothing else in the system needs to change (that is the point of the port)."""
from __future__ import annotations

import time

import httpx

from .base import BackendUnavailable


class GigSimBackend:
    def __init__(self, base_url: str, api_key: str, retries: int = 3, timeout: float = 10.0):
        self.http = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
        self.retries = retries

    def _req(self, method: str, path: str, **kw):
        for attempt in range(self.retries):
            try:
                r = self.http.request(method, path, **kw)
                if r.status_code == 429 or r.status_code >= 500:   # rate limit / 5xx -> backoff
                    raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
                r.raise_for_status()
                return r.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if attempt == self.retries - 1:
                    raise BackendUnavailable(str(exc)) from exc
                time.sleep(0.5 * 2 ** attempt)

    def search_jobs(self, query, limit): return self._req("GET", "/jobs", params={"q": query, "limit": limit})
    def get_job(self, job_id): return self._req("GET", f"/jobs/{job_id}")
    def get_client_history(self, client_id): return self._req("GET", f"/clients/{client_id}")
    def get_connects_balance(self): return self._req("GET", "/me/connects")["balance"]
    def list_messages(self, thread_id): return self._req("GET", f"/threads/{thread_id}/messages")
    def connects_cost(self, job_id): return self.get_job(job_id).get("connects_cost", 8)
    def create_proposal(self, job_id, cover_letter, amount, answers):
        return self._req("POST", "/proposals", json={"job_id": job_id, "cover_letter": cover_letter,
                                                     "amount": amount, "answers": answers})
    def submit_proposal(self, proposal_id): return self._req("POST", f"/proposals/{proposal_id}/submit")
    def send_message(self, thread_id, body): return self._req("POST", f"/threads/{thread_id}/messages", json={"body": body})
