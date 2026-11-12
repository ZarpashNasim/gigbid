"use client";
import { useEffect, useState, ReactNode } from "react";
import { getToken, setToken } from "@/lib/api/client";

/** Placeholder sign-in: paste the reviewer token. Replace with real multi-user auth. */
export default function TokenGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [val, setVal] = useState("");
  useEffect(() => setReady(!!getToken()), []);
  if (ready) return <>{children}</>;
  return (
    <form className="card" onSubmit={(e) => { e.preventDefault(); if (val.trim()) { setToken(val.trim()); setReady(true); } }}>
      <h2>Sign in</h2>
      <label htmlFor="token">Access token</label>
      <div className="row"><input id="token" type="password" value={val} onChange={(e) => setVal(e.target.value)} />
        <button className="primary" type="submit">Sign in</button></div>
    </form>
  );
}
