import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { Activity } from "lucide-react";

export default function LiveHistogram({ data = [] }) {
  if (!data.length) {
    return (
      <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="p-5 text-slate-400">No histogram data yet.</div>
      </div>
    );
  }

  const max = Math.max(...data.map((d) => d.count || 0));

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">
      <div className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Live Threat Activity</h2>
            <p className="text-sm text-slate-400">Intrusions per 2 seconds, updated smoothly.</p>
          </div>
          <Activity className="h-5 w-5 text-red-300" />
        </div>

        <div className="h-[340px] rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <defs>
                <linearGradient id="histBar" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#fb7185" stopOpacity={0.95} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.55} />
                </linearGradient>
              </defs>

              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="time" tick={{ fill: "#94a3b8", fontSize: 11 }} minTickGap={22} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  background: "#020617",
                  border: "1px solid #1f2937",
                  borderRadius: "12px",
                }}
              />
              <ReferenceLine
                y={max ? Math.ceil(max * 0.7) : 0}
                stroke="#334155"
                strokeDasharray="4 4"
              />
              <Bar
                dataKey="count"
                fill="url(#histBar)"
                radius={[8, 8, 0, 0]}
                animationDuration={700}
                animationEasing="ease-out"
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}