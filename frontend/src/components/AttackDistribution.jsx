import React from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { PieChart as PieIcon } from "lucide-react";

const COLORS = ["#fb7185", "#22d3ee", "#34d399", "#f59e0b", "#a78bfa", "#60a5fa", "#f97316", "#e879f9"];

export default function AttackDistribution({ data = [] }) {
  if (!data.length) {
    return (
      <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="p-5 text-slate-400">No distribution data yet.</div>
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">
      <div className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Attack Distribution</h2>
            <p className="text-sm text-slate-400">Which classes are appearing most often.</p>
          </div>
          <PieIcon className="h-5 w-5 text-cyan-300" />
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_1.1fr]">
          <div className="h-[260px] rounded-2xl border border-slate-800 bg-slate-950/60 p-2">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Tooltip
                  contentStyle={{
                    background: "#020617",
                    border: "1px solid #1f2937",
                    borderRadius: "12px",
                  }}
                />
                <Pie
                  data={data.slice(0, 6)}
                  dataKey="count"
                  nameKey="label"
                  innerRadius={62}
                  outerRadius={92}
                  paddingAngle={4}
                  stroke="#020617"
                >
                  {data.slice(0, 6).map((entry, index) => (
                    <Cell key={entry.label} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="space-y-2">
            {data.slice(0, 6).map((item, idx) => (
              <div
                key={item.label}
                className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-3 w-3 rounded-full"
                      style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                    />
                    <span className="text-sm font-medium text-slate-100">{item.label}</span>
                  </div>
                  <span className="text-sm text-slate-300">{item.share}%</span>
                </div>
                <div className="mt-2 h-2 rounded-full bg-slate-800">
                  <div
                    className="h-2 rounded-full"
                    style={{
                      width: `${Math.max(4, item.share)}%`,
                      backgroundColor: COLORS[idx % COLORS.length],
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}