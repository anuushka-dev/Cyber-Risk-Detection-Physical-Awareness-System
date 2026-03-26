import React from "react";
import { Clock3, ArrowRight, ShieldAlert } from "lucide-react";
import { formatTime, isBenign, labelTone } from "../utils/helpers";

export default function LiveFeed({ events = [] }) {
  const latest = events.slice(0, 12);

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">
      <div className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Live Event Log</h2>
            <p className="text-sm text-slate-400">Latest detections in a terminal-style stream.</p>
          </div>
          <ShieldAlert className="h-5 w-5 text-fuchsia-300" />
        </div>

        <div className="max-h-[685px] overflow-y-auto rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
          <div className="space-y-2">
            {latest.map((e) => {
              const benign = isBenign(e.label);

              return (
                <div
                  key={e.id}
                  className={`rounded-2xl border p-3 ${benign
                    ? "border-emerald-500/20 bg-emerald-500/5"
                    : "border-rose-500/20 bg-rose-500/5"
                    }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${labelTone(e.label)}`}>
                        {e.label}
                      </span>
                      <span className="text-xs text-slate-400">{formatTime(e.ts)}</span>
                    </div>
                    <span className="text-sm font-semibold text-slate-100">
                      {Number(e.confidence || 0).toFixed(4)}
                    </span>
                  </div>

                  <div className="mt-2 flex items-center gap-2 text-sm text-slate-200">
                    <span>{e.source_ip}</span>
                    <ArrowRight className="h-4 w-4 text-slate-500" />
                    <span>{e.dest_ip}</span>
                  </div>

                  <div className="mt-1 text-xs text-slate-400">Protocol: {e.protocol || "—"}</div>
                </div>
              );
            })}

            {!latest.length && (
              <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
                Waiting for live events...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
