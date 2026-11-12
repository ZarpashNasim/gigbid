"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, PendingApproval, RunDetail } from "@/lib/api/client";
import ApprovalPanel from "@/components/ApprovalPanel";
import EvidenceHover, { Ev } from "@/components/EvidenceHover";

export default function Studio() {
  const id = decodeURIComponent(String(useParams().id));
  const [d, setD] = useState<RunDetail | null>(null);
  const [pending, setPending] = useState<PendingApproval | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [detail, approvals] = await Promise.all([api.detail(id), api.approvals()]);
      setD(detail); setPending(approvals.find((a) => a.thread_id === id) ?? null); setErr(null);
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Unexpected error"); }
  }, [id]);
  useEffect(() => { load(); }, [load]);   // a refresh re-reads the pending approval from the server

  if (err) return <p className="bad" role="alert">{err}</p>;
  if (!d) return <p className="mut">Loading…</p>;
  if (!d.draft) return <div className="card">No draft for this job. Decision: {d.decision?.action} — {d.decision?.reason}</div>;

  const evById = new Map<string, Ev>();
  d.fit?.matches.forEach((m) => m.evidence.forEach((e) => evById.set(e.id, e as Ev)));

  // Split the letter into plain text and claim spans so each claim can show its evidence.
  const letter = d.draft.cover_letter; const parts: React.ReactNode[] = []; let at = 0;
  [...d.draft.claims].map((c) => ({ c, i: letter.indexOf(c.text) })).filter((x) => x.i >= 0).sort((a, b) => a.i - b.i)
    .forEach(({ c, i }) => {
      if (i < at) return;
      parts.push(letter.slice(at, i));
      parts.push(<EvidenceHover key={i} text={c.text} status={c.status}
        evidence={c.evidence_ids.map((e) => evById.get(e)).filter(Boolean) as Ev[]} />);
      at = i + c.text.length;
    });
  parts.push(letter.slice(at));

  return (
    <>
      <h1>{String(d.job?.title ?? "Proposal")}</h1>
      <section className="card"><h3>Cover letter</h3>
        <p style={{ whiteSpace: "pre-wrap" }} data-testid="letter">{parts}</p>
        <p className="mut">Hover or focus an underlined claim to see its evidence. Red = unsupported.</p></section>

      <section className="card"><h3>Requirement → evidence</h3>
        <ul>{d.fit?.matches.map((m, i) => (
          <li key={i}><span className={m.covered ? "ok" : "bad"}>{m.covered ? "✓" : "✗"}</span> {m.requirement}
            {m.evidence.length > 0 && <span className="mut"> — {m.evidence.map((e) => e.source).join(", ")}</span>}</li>))}</ul></section>

      {d.risk && d.risk.flags.length > 0 && <section className="card warn"><h3>Risk flags</h3><p>{d.risk.flags.join(", ")}</p></section>}
      {d.compliance && !d.compliance.allowed && <section className="card bad" role="alert">
        Blocked by Compliance: {d.compliance.violations.join(", ")}</section>}

      {pending
        ? <ApprovalPanel pending={pending} initialLetter={letter} onDone={load} />
        : <p className="mut">Status: {d.info.status}. Nothing pending approval.</p>}
    </>
  );
}
