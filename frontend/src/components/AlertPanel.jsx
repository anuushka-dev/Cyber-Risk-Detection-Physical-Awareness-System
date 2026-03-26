import React from "react";
import { AlertTriangle, Flame, Radio } from "lucide-react";
import { isBenign, labelTone } from "../utils/helpers";

export default function AlertPanel({ latest, topThreats, attackCount, soundEnabled }) {
  const attack = latest && !isBenign(latest.label);

  return (
    <div className="rounded-3xl border h-[640px] border-slate-800 bg-slate-900/70 backdrop-blur">
      <div className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Alert Panel</h2>
            <p className="text-sm text-slate-400">Latest detection and threat ranking.</p>
          </div>
          <AlertTriangle className={`h-5 w-5 ${attack ? "text-red-300" : "text-amber-300"}`} />
        </div>

        <div
          className={`rounded-2xl border p-4 shadow-lg transition ${
            attack
              ? "border-red-500/30 bg-red-500/10 shadow-red-500/20"
              : "border-emerald-500/20 bg-emerald-500/10 shadow-emerald-500/10"
          }`}
        >
          <div className="flex items-center gap-2">
            <div
              className={`h-3 w-3 rounded-full ${attack ? "bg-red-400 animate-pulse" : "bg-emerald-400"}`}
            />
            <h3 className={`text-lg font-bold ${attack ? "text-red-200" : "text-emerald-200"}`}>
              {attack ? `${latest.label.toUpperCase()} DETECTED!` : "NO ACTIVE ATTACK"}
            </h3>
          </div>

          <p className="mt-2 text-sm text-slate-200">
            {attack
              ? "The latest network event looks suspicious and has been flagged by the model."
              : "System is monitoring traffic normally right now."}
          </p>

          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-slate-300">Confidence</span>
            <span className="font-mono text-slate-100">
              {latest ? latest.confidence.toFixed(4) : "—"}
            </span>
          </div>

          <div className="mt-2 flex items-center justify-between text-sm">
            <span className="text-slate-300">Sound</span>
            <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${soundEnabled ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200" : "border-slate-700 bg-slate-800 text-slate-300"}`}>
              {soundEnabled ? "Enabled" : "Click Enable Sound"}
            </span>
          </div>
        </div>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200">Top Threats</h3>
            <span className="text-xs text-slate-400">{attackCount} attack events</span>
          </div>

          <div className="space-y-2">
            {topThreats.length ? (
              topThreats.slice(0, 3).map((t, idx) => (
                <div
                  key={t.label}
                  className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">{idx + 1}.</span>
                    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${labelTone(t.label)}`}>
                      {t.label}
                    </span>
                  </div>
                  <span className="text-sm font-semibold text-slate-100">{t.share}%</span>
                </div>
              ))
            ) : (
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-400">
                No threat distribution yet.
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-950/60 p-3 text-sm text-slate-300">
          <div className="flex items-center gap-2">
            <Flame className="h-4 w-4 text-orange-300" />
            <span>Attack events are highlighted with visual flash + sound.</span>
          </div>
          <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
            <Radio className="h-3.5 w-3.5" />
            <span>Real-time feed continues every 500ms.</span>
          </div>
        </div>
      </div>
    </div>
  );
}