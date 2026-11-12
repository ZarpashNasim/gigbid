"use client";
import { useState } from "react";

export type Ev = { id: string; type: string; source: string; text: string; outcome?: string | null };

/** A claim in the draft. Hover OR keyboard focus shows the evidence that supports it. */
export default function EvidenceHover({ text, status, evidence }: { text: string; status: string; evidence: Ev[] }) {
  const [open, setOpen] = useState(false);
  return (
    <span className={`claim ${status === "unsupported" ? "unsupported" : ""}`} tabIndex={0}
          onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
          onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)} data-testid="claim">
      {text}
      {open && (
        <span role="tooltip" className="pop">
          <strong>{status.replace("_", " ")}</strong>
          {evidence.length === 0 && <span className="bad"> — no supporting evidence</span>}
          {evidence.map((e) => (
            <span key={e.id} style={{ display: "block", marginTop: 6 }}>
              <span className="mut">{e.type} · {e.source}{e.outcome ? ` · ${e.outcome}` : ""}</span><br />{e.text}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}
