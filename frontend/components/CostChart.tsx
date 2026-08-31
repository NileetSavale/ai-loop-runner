"use client";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export function CostChart({ data }: { data: { date: string; cost_usd: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data}>
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
        <Tooltip formatter={(v: number) => [`$${v.toFixed(4)}`, "Cost"]} />
        <Line type="monotone" dataKey="cost_usd" stroke="#6366f1" dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}
