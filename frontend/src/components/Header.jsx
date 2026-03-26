import React from "react";
import { Activity, Bell, Pause, Play, RefreshCw, ShieldCheck, Volume2, VolumeX, Wifi } from "lucide-react";

export default function Header({
  health,
  modelInfo,
  running,
  onToggleRunning,
  onRefresh,
  soundEnabled,
  onEnableSound,
}) {
  const apiOk = health?.status === "ok";
  const modelOk = !!health?.model_loaded;

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-4 shadow-2xl shadow-slate-950/40 backdrop-blur">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/15 ring-1 ring-cyan-400/30">
            <Activity className="h-6 w-6 text-cyan-300" />
          </div>

          <div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
              AI IDS Dashboard
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Real-time intrusion detection with live threat visualization.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${
              apiOk
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                : "border-red-500/30 bg-red-500/10 text-red-200"
            }`}
          >
            <Wifi className="h-3.5 w-3.5" />
            API: {apiOk ? "ONLINE" : "OFFLINE"}
          </span>

          <span
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${
              modelOk
                ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-200"
                : "border-red-500/30 bg-red-500/10 text-red-200"
            }`}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            Model: {modelOk ? modelInfo?.model_name || "XGBoost" : "NOT LOADED"}
          </span>

          <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-800/80 px-3 py-1 text-xs font-medium text-slate-200">
            <Bell className="h-3.5 w-3.5 text-amber-300" />
            Features: {modelInfo?.feature_count || 45}
          </span>

          <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-800/80 px-3 py-1 text-xs font-medium text-slate-200">
            Uptime: {Number(health?.uptime_seconds || 0)}s
          </span>

          <button
            onClick={onToggleRunning}
            className="inline-flex items-center gap-2 rounded-full bg-slate-800 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
          >
            {running ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {running ? "Pause" : "Resume"}
          </button>

          <button
            onClick={onRefresh}
            className="inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>

          <button
            onClick={onEnableSound}
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
              soundEnabled
                ? "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/30"
                : "bg-red-500/15 text-red-200 ring-1 ring-red-500/30 hover:bg-red-500/20"
            }`}
          >
            {soundEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
            {soundEnabled ? "Sound On" : "Enable Sound"}
          </button>
          <button
            onClick={() => fetch("http://127.0.0.1:8000/demo/attack",{method:"POST"})}
              className="rounded-full bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-400"
          >

              🚨 Trigger Attack

          </button>

          <button
onClick={()=>fetch("http://127.0.0.1:8000/demo/attack?severity=low",{method:"POST"})}
className="rounded-full bg-amber-500/20 px-3 py-1 text-xs ring-1 ring-amber-500/40"
>
Scan
</button>

<button
onClick={()=>fetch("http://127.0.0.1:8000/demo/attack?severity=mid",{method:"POST"})}
className="rounded-full bg-orange-500/20 px-3 py-1 text-xs ring-1 ring-orange-500/40"
>
DoS
</button>

<button
onClick={()=>fetch("http://127.0.0.1:8000/demo/attack?severity=high",{method:"POST"})}
className="rounded-full bg-red-600/20 px-3 py-1 text-xs ring-1 ring-red-600/40"
>
Critical
</button>
        </div>
      </div>
    </div>
  );
}