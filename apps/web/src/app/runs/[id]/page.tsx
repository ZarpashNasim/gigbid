"use client";
import { useParams } from "next/navigation";
import RunTimeline from "@/components/RunTimeline";

export default function RunViewer() {
  const id = decodeURIComponent(String(useParams().id));
  return (<><h1>Agent run</h1><p className="mut">{id}</p><RunTimeline threadId={id} />
    <p><a href={`/api/runs/${encodeURIComponent(id)}/trace`}>Full trace (JSON)</a></p></>);
}
