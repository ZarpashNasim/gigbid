"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, RunInfo } from "@/lib/api/client";

export default function Messages() {
  const [rows, setRows] = useState<RunInfo[] | null>(null);
  const [tid, setTid] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setRows(await api.conversations()); setErr(null); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Unexpected error"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  async function draft(e: React.FormEvent) {
    e.preventDefault(); if (!tid.trim()) return;
    try { await api.startConversation(tid.trim()); setTid(""); await load(); }
    catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "Unexpected error"); }
  }
  return (
    <>
      <h1>Messages</h1>
      <form className="row" onSubmit={draft}>
        <label htmlFor="cid" className="mut">Conversation id</label>
        <input id="cid" value={tid} onChange={(e) => setTid(e.target.value)} placeholder="e.g. m1" />
        <button className="primary" type="submit">Draft reply</button>
      </form>
      {err && <p className="bad" role="alert">{err}</p>}
      {!rows && !err && <p className="mut">Loading…</p>}
      {rows && rows.length === 0 && <div className="card mut">No conversations yet. Enter a conversation id to draft a reply.</div>}
      {rows?.map((r) => (
        <article className="card" key={r.thread_id} data-testid="conv-card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>Conversation {r.job_id}</strong>
            <span className={`badge ${r.status === "flagged" ? "bad" : r.waiting_for_approval ? "warn" : ""}`}>{r.status}</span>
          </div>
          <a href={`/messages/${encodeURIComponent(r.thread_id)}`}>{r.waiting_for_approval ? "Review reply →" : "Open"}</a>
        </article>
      ))}
    </>
  );
}
