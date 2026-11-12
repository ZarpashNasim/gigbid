"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, RunDetail, RunInfo } from "@/lib/api/client";

type Row = { info: RunInfo; d: RunDetail };

export default function Inbox() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [jobId, setJobId] = useState("");
  const [hideSkips, setHideSkips] = useState(false);

  const load = useCallback(async () => {
    try {
      const runs = await api.runs();
      const details = await Promise.all(runs.map((r) => api.detail(r.thread_id)));
      const out = runs.map((info, i) => ({ info, d: details[i] }));
      out.sort((a, b) => (b.d.fit?.score ?? 0) - (a.d.fit?.score ?? 0));   // ranked by fit
      setRows(out); setErr(null);
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Unexpected error"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function analyse(e: React.FormEvent) {
    e.preventDefault(); if (!jobId.trim()) return;
    try { await api.start(jobId.trim()); setJobId(""); await load(); }
    catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "Unexpected error"); }
  }
  const shown = (rows ?? []).filter((r) => !(hideSkips && r.d.decision?.action === "skip"));
  return (
    <>
      <h1>Job inbox</h1>
      <form className="row" onSubmit={analyse}>
        <label htmlFor="jid" className="mut">Job id</label>
        <input id="jid" value={jobId} onChange={(e) => setJobId(e.target.value)} placeholder="e.g. job_123" />
        <button className="primary" type="submit">Analyse</button>
        <label className="row"><input type="checkbox" checked={hideSkips} onChange={(e) => setHideSkips(e.target.checked)} /> Hide skips</label>
      </form>
      {err && <p className="bad" role="alert">{err}</p>}
      {!rows && !err && <p className="mut">Loading…</p>}
      {rows && shown.length === 0 && <div className="card mut">No jobs yet. Enter a job id above, or wait for the next scheduled scout.</div>}
      {shown.map(({ info, d }) => {
        const risk = d.risk, act = d.decision?.action;
        return (
          <article className="card" key={info.thread_id} data-testid="job-card">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong>{String(d.job?.title ?? info.job_id)}</strong>
              <span className="badge">fit {(d.fit?.score ?? 0).toFixed(2)}</span>
            </div>
            <div className="row">
              <span className={`badge ${act === "bid" ? "ok" : act === "watch" ? "warn" : "bad"}`}>{act ?? "…"}</span>
              {risk?.scam && <span className="badge bad">scam</span>}
              {risk?.injection_detected && <span className="badge bad">injection</span>}
              {risk?.off_platform_ask && <span className="badge warn">off-platform</span>}
              {risk?.free_work_request && <span className="badge warn">free work</span>}
              {d.price && <span className="mut">${d.price.amount} · {d.price.connects_cost} Connects</span>}
            </div>
            <p className="mut">{d.decision?.reason}</p>
            <div className="row">
              {info.waiting_for_approval
                ? <a href={`/studio/${encodeURIComponent(info.thread_id)}`} className="badge warn">Review proposal →</a>
                : <a href={`/studio/${encodeURIComponent(info.thread_id)}`}>Open</a>}
              <a href={`/runs/${encodeURIComponent(info.thread_id)}`}>Run viewer</a>
              <span className="mut">{info.status}</span>
            </div>
          </article>
        );
      })}
    </>
  );
}
