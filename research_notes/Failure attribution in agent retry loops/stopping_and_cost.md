# Stopping rules, futile-retry detection, and the cost of wasted retries in LLM agent loops

Compiled 2026-11-06. Many 2026 sources are arXiv preprints, not peer-reviewed. Several summaries below come from abstract pages or tool-generated page summaries rather than full PDFs. Where that limits what can be said, it is noted.

## Q1. What stopping rules do coding agents use?

### Takeaway
Production agent frameworks use crude, mechanical stopping rules: per-instance cost caps, turn/iteration caps, and pattern-matching "stuck" detectors that catch repeated actions or errors. None of the ones examined decide to stop based on *why* the run is failing. Research on turn caps shows a cap near the 75th percentile of baseline turns cuts cost a lot while losing little resolve rate.

### Cited Findings
- **OpenHands SDK stuck detector** (enabled by default, `stuck_detection=True`). It flags:
  - the same action producing the same observation 4 or more times;
  - the same action producing an error 3 or more times;
  - 3 or more consecutive agent messages with no user input ("monologue");
  - two action-observation pairs alternating in a ping-pong pattern for 6 or more cycles;
  - repeated context-window errors.

  Actions are compared by tool name, content and thought, ignoring IDs. Only events after the last user message are examined. The application can query `conversation.stuck_detector.is_stuck()` and halt or take corrective action. — [OpenHands docs: Agent Stuck Detector](https://docs.openhands.dev/sdk/guides/agent-stuck-detector)
- A GitHub issue reported that the stuck thresholds were hardcoded and caused false positives, for example an agent that intentionally polls a command on a schedule and got halted. It proposed configurable thresholds. — [OpenHands software-agent-sdk issue #762](https://github.com/OpenHands/software-agent-sdk/issues/762)
- **SWE-agent cost caps.** `per_instance_cost_limit` is a USD cap per task. Exceeding it ends that instance and triggers autosubmit of the current patch. `total_cost_limit` stops all execution. A value of 0 disables a limit. The default value is inconsistent within the secondary source (3.0 vs 0). The loop ends on submit, exit, cost limit, timeout, or context overflow. — [DeepWiki: SWE-agent cost tracking and limits](https://deepwiki.com/scaleapi/SWE-agent/2.2.2-cost-tracking-and-limits); [DEV Community SWE-agent deep dive](https://dev.to/truongpx396/swe-agent-deep-dive-build-your-own-guide-ade) (both secondary; I did not read the official SWE-agent source)
- **Turn-control study: Gao & Peng (ByteDance), "More with Less", arXiv 2510.16786v2, Nov 2025, ICSE '26.** Setup:
  - TRAE Agent on a 100-task SWE-bench Verified subset.
  - Unlimited-turn baselines: Claude 4 Sonnet 75% resolved for $585 total ($7.80/solution); Gemini 2.5 Pro 63% for $408; GPT-4.1 62% for $322 ($5.19/solution).

  Results:
  - A turn cap at the **75th percentile** of baseline turns (with "turns left" reminders) gave:
    - Claude: −5.3% relative solve rate, −23.6% cost;
    - Gemini: +3.2% solve rate, −68.3% cost;
    - GPT-4.1: −8.1% solve rate, −38.4% cost.
  - A cap at the **25th percentile** hurt badly (Gemini −58.7% solve rate).
  - **Dynamic** limits, which start low and grant a one-time extension only if no patch exists yet, matched or beat fixed limits with a further 5–24% cost reduction.
  - Cost grows "non-linearly, often quadratically" with turns, because the whole history is resent each turn.
  - Leaderboard agents' median turns per instance were 41–58, with some tasks exceeding 175.
  - Caveats from the authors: single runs, no prompt caching in cost calculations.

  — [arXiv 2510.16786v2](https://arxiv.org/html/2510.16786v2)
- Benchmark operators also use exit statuses as stopping and retry signals. A SWE-rebench talk recommends explicit exit statuses (context exhaustion, excessive tool calls, provider errors). It says a retry policy must separate model-attributable failures from infrastructure failures, because rerunning failures can quietly change what the score measures. — [AI Engineer Europe 2026: SWE-rebench lessons](https://www.ai.engineer/talks/wcUJWP6WpGM-swe-rebench-lessons-from-evaluating-coding-agents)

### Inferences
- The framework stuck detectors are **syntactic**: they detect identical or alternating actions. They would not catch a loop where the agent makes *different* edits that keep failing the same tests for an external reason, such as a test that was already failing or a broken environment. A cause-aware stop rule addresses a gap these detectors leave open.
- Because per-turn cost grows with history length, late iterations are the most expensive ones. Futile late retries therefore cost more than proportionally.

### Gaps
- I did not verify the current SWE-agent default `per_instance_cost_limit` or `max_iterations` defaults in OpenHands' main app from primary source code.
- I did not check Claude Code / Codex CLI / Aider documentation for max-turn or retry defaults.

## Q2. Diminishing returns of self-repair, and cost-aware evaluation

### Takeaway
Across 2023–2026 studies, most of the gain from iterative self-repair arrives in the first 1–4 rounds and is near zero by about round 5–7. Once compute is counted, self-repair is often no better than resampling. Simple retry baselines can match or beat elaborate reflection agents at lower cost. Agent token use is highly variable, and spending more tokens does not reliably buy accuracy.

### Cited Findings
- **Olausson et al., "Is Self-Repair a Silver Bullet for Code Generation?"** (arXiv 2306.09896, June 2023; ICLR 2024).
  - Models and benchmarks: Code Llama, GPT-3.5 and GPT-4 on HumanEval and APPS.
  - When the cost of repair is taken into account, gains are "often modest, vary significantly between subsets of the data, and are sometimes not present at all."
  - The bottleneck is the quality of the model's feedback on its own code. Stronger-model or human feedback gave substantially larger gains.

  — [arXiv 2306.09896](https://arxiv.org/abs/2306.09896); [ICLR 2024 proceedings](https://proceedings.iclr.cc/paper_files/paper/2024/hash/9ddc141bdbf9d1db510cefff56c586ad-Abstract-Conference.html)
- Olausson et al. use a cost-normalised metric (pass@t, which counts tokens) instead of pass@k. A secondary review says this gives a less favorable picture of self-repair than pass@k. — [Liner review](https://liner.com/review/is-selfrepair-a-silver-bullet-for-code-generation) (secondary)
- **Self-Refine** (Madaan et al., arXiv 2303.17651, 2023): "the marginal improvement naturally decreases with more iterations." Code optimization went from 22.0 to 28.8 over 3 iterations, with most gains in the first iterations. — [arXiv 2303.17651](https://arxiv.org/pdf/2303.17651)
- **Arimbur, "How Many Tries Does It Take?"** (arXiv 2604.10508, Apr 2026). Seven models (Llama 3.1 8B to Gemini 2.5 Pro), HumanEval and MBPP, up to 5 repair attempts.
  - Self-repair added +4.9 to +17.1 pp on HumanEval and +16.0 to +30.0 pp on MBPP.
  - "Most gains concentrate in the first two" rounds. Another summary quotes 76–95% of total gain captured by two rounds; that figure comes from a secondary search snippet and I did not verify it.
  - Assertion (logic) errors were the hardest to repair, at about 45%. Syntax and name errors were repaired at much higher rates.

  — [arXiv 2604.10508](https://arxiv.org/abs/2604.10508)
- **Reichmann, Kang, An, Grunske et al., "Is Three the Magic Number? An Empirical Evaluation of LLM-Based Repair Loops"** (arXiv 2607.05197, ~Jul 2026). Tasks: code generation, test generation and translation. Models: Gemma-4 31B, Qwen3.5 27B, gpt-4o-mini.
  - The largest relative gain comes at step 1. By step 3, marginal gains are single-digit percent or lower.
  - The first 3–4 steps give most of the achievable gain, and improvement is near zero by steps 5–7.
  - Model gaps narrow with each step, but all curves flatten at about the same point.
  - The authors recommend treating the repair budget as an explicit, reported experimental variable. They give no explicit stopping rule.

  — [HF Papers 2607.05197](https://huggingface.co/papers/2607.05197)
- **Execution-guided self-debugging study** (Kim, *AI* journal 2026, DOI 10.3390/ai7100392):
  - Many revision requests return unchanged code.
  - Forcing a code change gave only +0.82 to +1.87 points.
  - Concrete failure feedback mattered more.
  - Repeated re-evaluation gives "further but diminishing" repair opportunities.

  — [citedrive listing](https://www.citedrive.com/en/discovery/inducing-code-change-in-llm-self-debugging-effects-on-program-repair/) (seen via search snippet only)
- **Kapoor, Stroebl, Siegel, Nadgir, Narayanan, "AI Agents That Matter"** (arXiv 2407.01502, July 2024).
  - Argues that accuracy-only leaderboards encourage unbounded cost, and proposes cost–accuracy Pareto reporting.
  - On HumanEval, a simple **Retry** baseline (re-call GPT-4 at temperature 0 up to 5 times when tests fail) reached 92.0% at a mean cost of $2.51. **Reflexion** (GPT-4) reached 87.8% at $3.90. Both are means over 5 runs on 164 problems.
  - Also proposes "Warming" (temperature rising from 0 to 0.5) and "Escalation" (cheap-to-expensive model) baselines.

  — [arXiv 2407.01502](https://arxiv.org/html/2407.01502v1); [project page](https://agents.cs.princeton.edu/)
- **Bai, Huang, Wang, Sun, Mihalcea, Brynjolfsson, Pentland, Pei, "How Do AI Agents Spend Your Money?"** (arXiv 2604.22750, Apr 2026; listed at NeurIPS 2026). Eight frontier LLMs on SWE-bench Verified.
  - Agentic coding uses about 1000× more tokens than code reasoning or chat, and input tokens dominate cost.
  - Runs on the same task vary by up to 30× in tokens.
  - Accuracy "often peaks at intermediate cost" and saturates at higher cost.
  - Kimi-K2 and Claude Sonnet 4.5 use more than 1.5M more tokens per task on average than GPT-5.
  - Models poorly predict their own token use (r ≤ 0.39) and systematically underestimate it.

  — [HF Papers 2604.22750](https://huggingface.co/papers/2604.22750); [NeurIPS 2026 listing](https://neurips.cc/virtual/2026/170688)
- **SWE-Effi** (arXiv 2509.09853, Sep 2025) argues that SWE-bench leaderboards rank only on resolve rate. It proposes effectiveness metrics under token and time budgets, noting that the most accurate agent is not necessarily the most effective in practice. — [alphaxiv 2509.09853](https://alphaxiv.org/abs/2509.09853) (abstract-level only)
- **SWE-Pruner** (arXiv 2601.16746, Jan 2026): on SWE-bench Verified, Claude Sonnet 4.5 spends 76.1% of its token budget on reads, and GLM-4.6 spends 67.5%. — [arXiv 2601.16746](https://arxiv.org/pdf/2601.16746) (search snippet)
- **Code agent behavior study** (arXiv 2511.00197, Oct 2025): failed SWE-bench trajectories tend to be longer and more variable than successful ones. — [alphaxiv 2511.00197](https://www.alphaxiv.org/abs/2511.00197v1) (snippet; a "30–50% savings" figure there is from an auto-generated overview and should not be used)

### Inferences
- Several independent lines of evidence point to a **default budget of about 2–4 test-feedback repair rounds**:
  - curves flattening by round 2–4 in function-level repair;
  - the 75th-percentile turn cap on SWE-bench;
  - accuracy saturating at intermediate token cost.

  Beyond that budget, extra rounds mostly add cost. This is an inference across different task granularities (function-level vs repository-level), not a single measured result.
- Because failed runs are longer, a large share of total spend on a benchmark plausibly goes to runs that never succeed. I found no source that quantifies this share for SWE-bench directly.

### Gaps
- I did not retrieve Olausson et al.'s exact pass@t tables or their finding on initial-sample vs repair budget split. From memory, they favour more diverse initial samples over many repairs per sample, but this is **unverified** here.
- I did not search for Self-Debugging (Chen et al. 2023) or Reflexion's per-iteration curves specifically.
- I did not access SWE-bench leaderboard per-submission cost reports.

## Q3. Learning or predicting when a trajectory will fail (early termination)

### Takeaway
2026 saw a cluster of preprints that train monitors or probes to abort doomed agent episodes early. On SWE-bench Verified the reported savings are modest (about 15–20% of tokens at a 5% false-positive rate). Larger savings come from hidden-state probes on toy environments. Restarting after an abort can raise the resolve rate.

### Cited Findings
- **Wang, Lyu, He, Yang, Zhong, Harel, Lo, "Fail-Fast, Restart-Smart"** (arXiv 2608.03222, 4 Aug 2026).
  - **Monitor (FailFast).** A 0.6B model predicts failure from observable trajectory prefixes, with no logits or hidden states. It is trained on Qwen3.6-27B trajectories with terminal and dense fail-to-pass supervision.
  - **Savings.** At a 5% target false-positive rate it saves 14.6–20.4% of execution tokens across policies, including a closed-API model it was not trained on. This beats an adapted per-step "AgentStop" baseline (12.5% on Qwen).
  - **Restart (RestartSmart).** After an alarm it restarts a fresh rollout and optionally offers the interrupted diff as an overlay. At a 25% FPR this raised resolution from 66.6% to 71.8%, while a cold restart gave 66.8%.
  - Failed runs show longer, redundant exploration or looping.

  — [arXiv 2608.03222](https://arxiv.org/abs/2608.03222)
- **"Doomed from the Start: Early Abort of LLM Agent Episodes via a Recall-Controlled Probe Cascade"** (arXiv 2607.06503, Jul 2026).
  - Linear probes on hidden activations predict failure from the first round. Behavior-only scorers are near chance that early.
  - A cascade of calibrated per-round gates controls episode-level recall of successful runs.
  - On TextCraft at 90% recall it saved 47.1% (Qwen-2.5-7B) and 37.2% (Llama-3.2-3B) of compute, which is 1.5–8.8× more than the best single-gate baseline.
  - The evaluation covers only TextCraft, not software tasks.

  — [arXiv 2607.06503](https://arxiv.org/pdf/2607.06503); [alphaxiv](https://www.alphaxiv.org/abs/2607.06503v2)
- **EarlyEval** (arXiv 2609.02783, Sep 2026) scores partial trajectories with separate success and failure predictors and stops when either is confident. It targets *evaluation* cost on SWE-bench and Terminal-Bench. — [alphaxiv 2609.02783](https://www.alphaxiv.org/abs/2609.02783) (search snippet only; numbers not retrieved)
- **ATROPOS** (arXiv 2604.15075) predicts early termination of eventually failing self-consistency inferences, with 0.85 accuracy at the midpoint, paired with model hot-swapping. — [arXiv 2604.15075](https://arxiv.org/pdf/2604.15075) (snippet)
- **AgentForesight** (arXiv 2605.08715) does online auditing for early failure prediction in multi-agent systems. — [arXiv 2605.08715](https://arxiv.org/pdf/2605.08715) (title and snippet only)

### Inferences
- The learned predictors forecast *that* a run will fail, not *why*. A false abort costs a run that would have succeeded, so these methods are tuned to false-positive budgets.
- A cause-based rule can complement them. For example, "the remaining failures were already failing before any edit" is a deterministic, near-zero-FPR signal for one specific class of futility.

### Gaps
- I did not search specifically for process reward models or verifiers for SWE-agent trajectories (for example, the SWE-Gym verifier or OpenHands critic models). They are relevant but not covered here.
- No independent replication of any of these early-abort results was found.

## Q4. Tying stopping decisions to the cause of failure

### Takeaway
Work on attributing failures to the agent vs the task or environment exists, but it is aimed at **benchmark diagnostics and retry policy for evaluators**, not at in-loop stopping. I found no published agent loop that stops retrying *because* it has attributed the failure to something outside the agent's control. This appears to be an open niche.

### Cited Findings
- **Hu, Shukla, Huang, "Verifying the Verifiers: Failure Attribution for Agentic Benchmark Diagnostics and Training Data Curation"** (ICLR 2026 Lifelong Agents workshop, Apr 2026).
  - Proposes a taxonomy separating agent limitations from task defects: ambiguous specs, flaky tests, broken environments.
  - Humans reached κ = 0.929 agreement.
  - **AutoTriage**, an agentic judge with sandbox execution (GPT-5.2 Codex), reached κ = 0.833.
  - Weaker triage models **over-attribute failures to task defects**, building plausible defenses of the agent.

  — [ICLR 2026 virtual page](https://iclr.cc/virtual/2026/10012540)
- **SWE-Cycle** (arXiv 2605.13139, 2026): nearly a third of disagreements stem from evaluation-pipeline failures independent of solution quality. Examples are a Gradle output format the SWE-bench parser could not read, and a Maven daemon cold-start timeout. — [arXiv 2605.13139](https://arxiv.org/pdf/2605.13139) (search snippet)
- **SWE-Next** (arXiv 2603.20691): after making environment profiles reusable, residual environment and harness failures were 2.4% of all failures. — [arXiv 2603.20691](https://arxiv.org/pdf/2603.20691) (snippet)
- **SWE-Marathon** (arXiv 2606.07682) excluded infrastructure crashes (141 trials with zero episodes) before classifying agent failures. — [arXiv 2606.07682](https://arxiv.org/pdf/2606.07682) (snippet)
- **SWE-rebench talk**: retry policy must separate model-attributable failures from infrastructure failures, using explicit exit statuses. — [AI Engineer Europe 2026](https://www.ai.engineer/talks/wcUJWP6WpGM-swe-rebench-lessons-from-evaluating-coding-agents)
- **OpenHands' stuck detector** includes an "action → error repeated 3 times" rule. That rule is the closest framework feature to cause-awareness, but it keys on identical errors, not attributed causes. — [OpenHands docs](https://docs.openhands.dev/sdk/guides/agent-stuck-detector)

### Inferences
- **The "Verifying the Verifiers" bias result is a caution for designs that use an LLM to decide "this isn't my fault, stop."** Weaker models over-blame the task. A deterministic signal such as baseline test-failure comparison is safer than LLM self-attribution.
- The share of failures that are not the agent's fault varies widely by harness quality: from about 2.4% (SWE-Next, curated environments) to about a third of evaluation disagreements (SWE-Cycle). How much cause-based stopping saves therefore depends on the environment.

### Gaps
- Searched: "coding agent failures environment setup errors not agent fault SWE-bench infrastructure failure attribution retry", plus early-termination queries. I found no paper that uses failure attribution as an **in-loop stopping criterion** for a coding agent, and no quantification of tokens wasted on retries against already-failing or flaky tests. This absence rests on a limited search (about 10 queries), not an exhaustive survey.
- I did not search for flaky-test detection literature (for example, rerun-based flakiness detection) as applied to agent loops.
