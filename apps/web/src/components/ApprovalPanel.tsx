"use client";
import { useState } from "react";
import { api, PendingApproval } from "@/lib/api/client";

/** Approve / edit / reject. Shows the dry_run preview: exactly what will be sent and what it costs. */
export default function ApprovalPanel({ pending, initialLetter, onDone }:
  { pending: PendingApproval; initialLetter: string; onDone: () => void }) {
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [letter, setLetter] = useState(initialLetter);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const p: any = pending.payload;
  const isMessage = p.kind === "message_approval";
  const issues: string[] = p.critic_open_issues ?? [];

  async function send(body: Parameters<typeof api.resolve>[1]) {
    setBusy(true); setErr(null);
    try { await api.resolve(pending.thread_id, body); onDone(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  return (
    <section className="card" aria-label="Approval">
      <h3>{isMessage ? "Send this reply?" : "Ready to send?"}</h3>
      {!isMessage && <p>Price <strong>${p.dry_run.amount}</strong> · Connects cost <strong>{p.dry_run.connects_cost}</strong></p>}
      <details><summary>Exactly what will be sent (dry run)</summary>
        <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(p.dry_run.payload, null, 2)}</pre></details>
      {issues.length > 0 && <p className="warn">Critic still has concerns: {issues.join("; ")}</p>}
      {p.price_rationale && <p className="mut">Price rationale: {p.price_rationale}</p>}
      {mode === "edit" && <textarea aria-label={isMessage ? "Edit reply" : "Edit cover letter"} value={letter} onChange={(e) => setLetter(e.target.value)} />}
      {mode === "reject" && <input aria-label="Rejection reason" placeholder="Why? (helps GigBid learn)" value={reason} onChange={(e) => setReason(e.target.value)} />}
      <div className="row" style={{ marginTop: 10 }}>
        {mode === "view" && <>
          <button className="primary" disabled={busy} onClick={() => send({ decision: "approve" })}>Approve</button>
          <button disabled={busy} onClick={() => setMode("edit")}>Edit</button>
          <button disabled={busy} onClick={() => setMode("reject")}>Reject</button></>}
        {mode === "edit" && <>
          <button className="primary" disabled={busy} onClick={() => send({ decision: "edit", edited_cover_letter: letter })}>Approve edited version</button>
          <button onClick={() => setMode("view")}>Cancel</button></>}
        {mode === "reject" && <>
          <button className="primary" disabled={busy || !reason.trim()} onClick={() => send({ decision: "reject", reason })}>Reject</button>
          <button onClick={() => setMode("view")}>Cancel</button></>}
      </div>
      {err && <p className="bad" role="alert">{err}</p>}
    </section>
  );
}
