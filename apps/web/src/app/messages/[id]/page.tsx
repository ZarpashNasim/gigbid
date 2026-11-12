"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, ConvDetail, PendingApproval } from "@/lib/api/client";
import ApprovalPanel from "@/components/ApprovalPanel";

export default function Conversation() {
  const id = decodeURIComponent(String(useParams().id));
  const [d, setD] = useState<ConvDetail | null>(null);
  const [pending, setPending] = useState<PendingApproval | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [detail, approvals] = await Promise.all([api.conversation(id), api.approvals()]);
      setD(detail); setPending(approvals.find((a) => a.thread_id === id) ?? null); setErr(null);
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Unexpected error"); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (err) return <p className="bad" role="alert">{err}</p>;
  if (!d) return <p className="mut">Loading…</p>;
  return (
    <>
      <h1>Conversation {d.info.job_id}</h1>
      <section className="card" aria-label="Thread">
        {d.messages.map((m, i) => (
          <p key={i}><strong>{String(m.from)}:</strong> {String(m.body)}</p>))}
      </section>
      {d.intent && <p>Intent: <span className={`badge ${d.intent.intent === "scam_signal" ? "bad" : ""}`} data-testid="intent">{d.intent.intent}</span>
        <span className="mut"> {d.intent.summary}</span></p>}
      {d.info.status === "flagged" && <section className="card bad" role="alert">
        Flagged as a possible scam or injection. No reply was drafted and nothing was sent.</section>}
      {d.draft && (
        <section className="card"><h3>Suggested reply</h3>
          <p style={{ whiteSpace: "pre-wrap" }} data-testid="reply">{d.draft.body}</p>
          {d.draft.proposed_slots.length > 0 && <><strong>Interview slots (from your calendar)</strong>
            <ul>{d.draft.proposed_slots.map((s) => <li key={s}>{s}</li>)}</ul></>}
        </section>)}
      {d.compliance && !d.compliance.allowed && <section className="card bad" role="alert">
        Blocked by Compliance: {d.compliance.violations.join(", ")}</section>}
      {pending ? <ApprovalPanel pending={pending} initialLetter={d.draft?.body ?? ""} onDone={load} />
        : <p className="mut">Status: {d.info.status}.</p>}
    </>
  );
}
