import type { CascadeStep } from "@/lib/types";

type Tone = "idle" | "active" | "good" | "bad" | "skipped";

const TONES: Record<Tone, string> = {
  idle: "border-gray-200 bg-white text-gray-400",
  active: "border-blue-300 bg-blue-50 text-blue-700",
  good: "border-green-300 bg-green-50 text-green-700",
  bad: "border-red-300 bg-red-50 text-red-700",
  skipped: "border-gray-200 bg-gray-50 text-gray-400",
};

export function shortName(model: string) {
  const name = model.replace(/^claude-/, "").replace(/-(\d+)-(\d+)$/, " $1.$2");
  return name.charAt(0).toUpperCase() + name.slice(1);
}

// The three steps of a cascade session: the cheap model's attempt, the review of a passing fix, and the main model
export function CascadeTrack({ steps, finalStatus }: { steps: CascadeStep[]; finalStatus: string | null }) {
  const find = (step: CascadeStep["step"]) => steps.find((s) => s.step === step);
  const scout = find("scout"), cheap = find("cheap"), review = find("review"), reviewed = find("reviewed");
  const escalated = find("escalated");
  const cheapModel = (cheap ?? scout)?.model ?? "";
  const reviewer = (reviewed ?? review)?.model ?? "claude-sonnet-5-5";
  const cost = steps.reduce((sum, s) => sum + (s.cost_usd ?? 0), 0);

  let first: [Tone, string];
  if (!cheap) first = ["active", "Exploring the repo"];
  else if (reviewed || review) first = ["good", "Its fix passed the tests"];
  else if (escalated) first = ["bad", "Its fix didn't pass the tests"];
  else first = ["active", "Trying the fix"];

  let second: [Tone, string];
  if (reviewed) second = reviewed.accept ? ["good", "Accepted the fix"] : ["bad", "Rejected the fix"];
  else if (review) second = ["active", "Reading the diff"];
  else if (escalated) second = ["skipped", "Skipped: nothing passed to review"];
  else second = ["idle", "Waits for a passing fix"];

  let third: [Tone, string];
  if (reviewed?.accept) third = ["skipped", "Not needed"];
  else if (!escalated) third = ["idle", "Only if the fix fails or is rejected"];
  else if (finalStatus === "passed") third = ["good", "Its fix passed the tests"];
  else if (finalStatus) third = ["bad", finalStatus === "cancelled" ? "Stopped" : "Its fix didn't pass the tests"];
  else third = ["active", "Starting over from the original code"];

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold text-gray-900">Cascade</h2>
        {cost > 0 && <span className="text-xs text-gray-400">scout and review: ${cost.toFixed(4)}</span>}
      </div>
      <ol className="grid gap-2 sm:grid-cols-3">
        <Card n={1} title={`${shortName(cheapModel)} tries first`} tone={first} />
        <Card n={2} title={`${shortName(reviewer)} reviews`} tone={second} />
        <Card n={3} title={escalated ? `${shortName(escalated.model)} redoes it` : "The main model redoes it"} tone={third} />
      </ol>
      {reviewed?.why && (
        <p className="text-xs text-gray-600">
          <span className="font-medium">Reviewer:</span> {reviewed.why}
          {!!reviewed.edited_tests?.length && (
            <span className="block text-gray-400">Changes existing tests: {reviewed.edited_tests.join(", ")}</span>
          )}
        </p>
      )}
      {escalated && (
        <p className="text-xs text-gray-600">
          Escalated after {escalated.cheap_iterations} attempt{escalated.cheap_iterations === 1 ? "" : "s"} because{" "}
          {escalated.reason}. The cheap attempt was undone.
        </p>
      )}
      {cheap?.notes && (
        <details>
          <summary className="text-xs cursor-pointer text-gray-500 font-medium">What the scout found</summary>
          <pre className="mt-1 p-2 bg-gray-50 rounded text-xs overflow-x-auto whitespace-pre-wrap">{cheap.notes}</pre>
        </details>
      )}
    </div>
  );
}

function Card({ n, title, tone: [tone, text] }: { n: number; title: string; tone: [Tone, string] }) {
  return (
    <li className={`border rounded-md px-3 py-2 ${TONES[tone]}`}>
      <p className="text-xs font-medium text-gray-900">
        <span className="text-gray-400 mr-1">{n}</span>
        {title}
      </p>
      <p className={`text-xs mt-0.5 ${tone === "active" ? "animate-pulse" : ""}`}>{text}</p>
    </li>
  );
}
