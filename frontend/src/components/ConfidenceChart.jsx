import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { TrendingUp } from "lucide-react";

export default function ConfidenceChart({ data = [] }) {
  if (!data.length) {
    return (
      <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="p-5 text-slate-400">No confidence data yet.</div>
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">
      <div className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Model Performance</h2>
            <p className="text-sm text-slate-400">Confidence trend and attack rate over time.</p>
          </div>
          <TrendingUp className="h-5 w-5 text-cyan-300" />
        </div>

        <div className="h-[300px] rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="time" tick={{ fill: "#94a3b8", fontSize: 11 }} minTickGap={24} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} domain={[0, 1]} />
              <Tooltip
                contentStyle={{
                  background: "#020617",
                  border: "1px solid #1f2937",
                  borderRadius: "12px",
                }}
              />
              <Legend />
              <Line
                type="natural"
                dataKey="avgConfidence"
                stroke="#22d3ee"
                strokeWidth={3}
                dot={false}
                name="Confidence"
              />
              <Line
                type="natural"
                dataKey="attackRate"
                stroke="#fb7185"
                strokeWidth={3}
                dot={false}
                name="Attack Rate"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}