"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

/** Degraded-mode banner: shown when the API (or marketplace behind it) is unreachable. */
export default function HealthBanner() {
  const [down, setDown] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const check = async () => {
      try { const h = await api.health(); if (alive) setDown(h.ok && h.marketplace === "up" ? null : "Marketplace unavailable. New jobs are queued and will resume automatically."); }
      catch { if (alive) setDown("Cannot reach the GigBid API. Your pending approvals are safe and will reappear."); }
    };
    check(); const t = setInterval(check, 10000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  return down ? <div role="alert" className="banner" data-testid="degraded-banner">{down}</div> : null;
}
