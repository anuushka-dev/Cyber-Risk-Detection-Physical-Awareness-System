import React from "react";
import { Activity, ShieldAlert, ShieldCheck, Gauge } from "lucide-react";

function MetricCard({ title, value, icon: Icon, accent }) {
  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-11 backdrop-blur">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{title}</div>
          <div className="mt-3 text-3xl font-semibold text-white">{value}</div>
        </div>
        <div className={`rounded-2xl border p-3 ${accent}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}

export default function MetricsCards({ total, attacks, benign, avgConfidence }) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <MetricCard title="Total Events" value={total.toLocaleString()} icon={Activity} accent="border-cyan-500/20 bg-cyan-500/10 text-cyan-200" />
      <MetricCard title="Attack Events" value={attacks.toLocaleString()} icon={ShieldAlert} accent="border-rose-500/20 bg-rose-500/10 text-rose-200" />
      <MetricCard title="Benign Events" value={benign.toLocaleString()} icon={ShieldCheck} accent="border-emerald-500/20 bg-emerald-500/10 text-emerald-200" />
      <MetricCard title="Avg Confidence" value={avgConfidence.toFixed(3)} icon={Gauge} accent="border-amber-500/20 bg-amber-500/10 text-amber-200" />
    </div>
  );
}