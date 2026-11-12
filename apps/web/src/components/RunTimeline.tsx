"use client";
import { useEffect, useState } from "react";
import { streamRun } from "@/lib/api/client";

type Ev = { node: string; update?: any };

/** Live node-by-node progress streamed from LangGraph (via the API's SSE). Never a bare spinner. */
export default function RunTimeline({ threadId }: { threadId: string }) {
  const [nodes, setNodes] = useState<Ev[]>([]);
  const [end, setEnd] = useState<{ status: string | null; waiting_for_approval: boolean } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const ctl = new AbortController();
    streamRun(threadId, (kind, data) => {
      if (kind === "node") setNodes((n) => [...n, data]);
      if (kind === "end") setEnd(data);
      if (kind === "error") setErr(data.error);
    }, ctl.signal).catch((e) => { if (!ctl.signal.aborted) setErr(String(e.message ?? e)); });
    return () => ctl.abort();
  }, [threadId]);
  return (
    <div className="card" aria-live="polite">
      <ol className="timeline" data-testid="timeline">
        {nodes.map((n, i) => <li key={i}><strong>{n.node}</strong> <span className="mut">done</span></li>)}
      </ol>
      {!end && !err && <p className="mut">Running… waiting for the next step.</p>}
      {end && <p className={end.waiting_for_approval ? "warn" : "ok"}>
        {end.waiting_for_approval ? "Waiting for your approval." : `Finished: ${end.status}`}</p>}
      {err && <p className="bad" role="alert">{err}</p>}
    </div>
  );
}
