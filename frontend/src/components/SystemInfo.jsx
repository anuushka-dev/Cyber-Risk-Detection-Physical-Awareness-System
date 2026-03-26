import React from "react";
import { Database, ShieldCheck, TimerReset, Radar, ServerCog } from "lucide-react";
import { formatTime, isBenign } from "../utils/helpers";

export default function SystemInfo({ health, modelInfo, events, lastRefresh }) {
  const recentAlerts = events.filter((e) => !isBenign(e.label)).slice(-3).reverse();

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">System Info</h2>
              <p className="text-sm text-slate-400">Model and runtime snapshot.</p>
            </div>
            <ServerCog className="h-5 w-5 text-cyan-300" />
          </div>

          <div className="space-y-3">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Model</span>
                <span className="font-semibold text-slate-100">{modelInfo?.model_name || "XGBoost"}</span>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Features</span>
                <span className="font-semibold text-cyan-200">{modelInfo?.feature_count || 45}</span>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Classes</span>
                <span className="font-semibold text-cyan-200">{modelInfo?.classes?.length || 14}</span>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">API</span>
                <span
                  className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                    health?.status === "ok"
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                      : "border-red-500/30 bg-red-500/10 text-red-200"
                  }`}
                >
                  {health?.status === "ok" ? "ONLINE" : "OFFLINE"}
                </span>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Uptime</span>
                <span className="font-mono text-slate-100">{Number(health?.uptime_seconds || 0)}s</span>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Last refresh</span>
                <span className="font-mono text-slate-100">{formatTime(lastRefresh)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Recent Alerts</h2>
              <p className="text-sm text-slate-400">Latest non-BENIGN detections.</p>
            </div>
            <Radar className="h-5 w-5 text-red-300" />
          </div>

          <div className="space-y-2">
            {recentAlerts.length ? (
              recentAlerts.map((a) => (
                <div key={a.id} className="rounded-2xl border border-red-500/20 bg-red-500/10 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-semibold text-red-100">{a.label}</span>
                    <span className="font-mono text-sm text-red-100">{a.confidence.toFixed(4)}</span>
                  </div>
                  <div className="mt-2 text-xs text-slate-300">
                    {a.source_ip} → {a.dest_ip} • {formatTime(a.ts)}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
                No attack alerts yet.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}