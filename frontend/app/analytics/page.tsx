import { api } from "@/lib/api";
import { CostChart } from "@/components/CostChart";
import { IterationChart } from "@/components/IterationChart";
import { CorrectionTax } from "@/components/CorrectionTax";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const [summary, costData, iterData, successData, topTasks] = await Promise.all([
    api.analytics.summary().catch(() => null),
    api.analytics.costOverTime().catch(() => []),
    api.analytics.iterationDistribution().catch(() => []),
    api.analytics.successRate().catch(() => null),
    api.analytics.topTasks().catch(() => []),
  ]);

  return (
    <div className="space-y-8">
      <h1 className="text-xl font-bold text-gray-900">Analytics</h1>

      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Total tokens", value: summary.total_tokens.toLocaleString() },
            { label: "Total cost", value: `$${summary.total_cost_usd.toFixed(2)}` },
            { label: "Avg cost/session", value: `$${summary.avg_cost_per_session.toFixed(4)}` },
            { label: "Success rate", value: `${(summary.success_rate * 100).toFixed(0)}%` },
          ].map((stat) => (
            <div key={stat.label} className="bg-white border rounded-lg p-4">
              <p className="text-xs text-gray-500">{stat.label}</p>
              <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Cost over time</h2>
          <CostChart data={costData} />
        </div>

        <div className="bg-white border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Iteration distribution</h2>
          <IterationChart data={iterData} />
        </div>

        {successData && (
          <div className="bg-white border rounded-lg p-4 flex flex-col items-center justify-center gap-4">
            <h2 className="text-sm font-semibold text-gray-700 self-start">Success rate</h2>
            <div className="flex gap-8 text-center">
              {[
                { label: "Passed", value: successData.passed, color: "text-green-600" },
                { label: "Failed", value: successData.failed, color: "text-red-500" },
                { label: "Stopped", value: successData.stopped, color: "text-gray-500" },
              ].map((s) => (
                <div key={s.label}>
                  <p className={`text-3xl font-bold ${s.color}`}>{s.value}</p>
                  <p className="text-xs text-gray-500">{s.label}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {summary && (
          <div className="bg-white border rounded-lg p-4 flex flex-col items-center justify-center">
            <h2 className="text-sm font-semibold text-gray-700 self-start mb-4">Correction tax</h2>
            <CorrectionTax value={summary.correction_tax_avg_iterations} />
          </div>
        )}
      </div>

      {topTasks.length > 0 && (
        <div className="bg-white border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Top 10 most expensive sessions</h2>
          <div className="space-y-2">
            {topTasks.map((t) => (
              <div key={t.id} className="flex items-center gap-3">
                <span className="flex-1 text-sm text-gray-700 truncate">{t.name}</span>
                <span className="text-xs text-gray-400">{t.total_tokens.toLocaleString()} tok</span>
                <span className="text-sm font-mono text-indigo-600">${t.total_cost_usd.toFixed(4)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
