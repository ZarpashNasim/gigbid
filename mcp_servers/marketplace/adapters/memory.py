"""In-memory backend for tests/offline demos."""
from __future__ import annotations


class MemoryBackend:
    def __init__(self, jobs=None, clients=None, connects=100):
        self.jobs, self.clients, self.connects = jobs or {}, clients or {}, connects
        self.proposals: dict[str, dict] = {}
        self.sent: list[dict] = []
        self.write_calls = 0

    def search_jobs(self, query, limit):
        return [j for j in self.jobs.values() if query.lower() in (j["title"] + j["description"]).lower()][:limit]
    def get_job(self, job_id): return self.jobs[job_id]
    def get_client_history(self, client_id): return self.clients.get(client_id, {})
    def get_connects_balance(self): return self.connects
    def list_messages(self, thread_id): return [m for m in self.sent if m["thread_id"] == thread_id]
    def connects_cost(self, job_id): return self.jobs[job_id].get("connects_cost", 8)
    def create_proposal(self, job_id, cover_letter, amount, answers):
        self.write_calls += 1
        self.connects -= self.connects_cost(job_id)
        pid = f"prop_{len(self.proposals)+1}"
        self.proposals[pid] = {"proposal_id": pid, "job_id": job_id, "status": "draft"}
        return self.proposals[pid]
    def submit_proposal(self, proposal_id):
        self.write_calls += 1
        self.proposals[proposal_id]["status"] = "submitted"
        return self.proposals[proposal_id]
    def send_message(self, thread_id, body):
        self.write_calls += 1
        m = {"thread_id": thread_id, "body": body}
        self.sent.append(m)
        return m
