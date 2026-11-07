# LogAct and log-, checkpoint- and voter-based frameworks for agent reliability

Research date: 2026-11-06. The LogAct text was read in full from the arXiv HTML (https://arxiv.org/html/2604.07988v1), which was downloaded and converted to plain text. The PDF (https://arxiv.org/pdf/2604.07988v1, 14 pages, cs.DC/cs.AI) was downloaded too, but no PDF text extractor was available in this environment. The HTML is the same v1 paper, and all quotes below come from it.

## Q1. What are LogAct's components, results and stated limitations or future work?

### Takeaway
LogAct (Meta, arXiv v1 dated 9 Apr 2026) turns each agent into a state machine split across several processes (Driver, Voters, Decider, Executor). These processes talk to each other only through a typed, durable, append-only shared log called the AgentBus. Every action is logged as an "intention" and must collect a quorum of votes before it runs. Its most novel idea is "agentic introspection": an LLM reasons over the log itself, which enables semantic recovery, history-aware voting and swarm supervision. The paper covers a single agent only. It names multi-agent coordination protocols as future work. It does not discuss retry loops, repeated failures, test suites or test-driven coding agents, and it describes coding agents on git as the easy case.

### Cited Findings

**Bibliographic details**
- Authors: Mahesh Balakrishnan, Ashwin Bharambe, Davide Testuggine, David Geraghty, David Mao, Vidhya Venkat, Ilya Mironov, Rithesh Baradi, Gayathri Aiyer and Victoria Dudin. v1 was submitted 9 Apr 2026, and it was still the only version when checked. — [arXiv abs](https://arxiv.org/abs/2604.07988)
- A reference implementation is open source under the MIT license as a Rust workspace (facebookresearch/logact). Its parts are `bus/` (AgentBus), `logact/commit_service/` and `plugins/logact-oss/`, which provides "local LogAct hooks for Claude Code, Codex, and Muse Code". The README describes "Preview macOS packages for local evaluation". — [GitHub README](https://github.com/facebookresearch/logact/blob/main/README.md)
- Balakrishnan presented LogAct at HPTS 2026, and Murat Demirbas's blog summarized the talk (Oct 2026). The summary's framing: "Agents corrupt state, crash mid-change, and overwrite each other". An agent is "a self-writing program", so the guarantees are built around "the record of what it did". The summary does not mention critiques or limitations. — [Murat Demirbas, HPTS 2026 Day 1](http://muratbuffalo.blogspot.com/2026/10/hpts-2026-day-1.html)

**Problem framing (verbatim)**
- "These concerns are tractable when a single agent operates on a transactional, sandboxed environment (e.g., a coding agent operating on scoped tasks against a git repository); but daunting when agents execute against a shared, distributed environment consisting of many stateful services." — [LogAct §1](https://arxiv.org/html/2604.07988v1)
- "Importantly, these challenges cannot be overcome just by using more intelligent models or more capable agentic harnesses: even an omniscient and omnipotent agent is subject to failures and asynchrony." — [LogAct §1](https://arxiv.org/html/2604.07988v1)
- "Failures can be semantically complex, involving not just crashes or unresponsiveness to pings, but also hallucinations, slow or buggy generated code, and complex actions whose safety depends deeply on context, control flow, and history." — [LogAct §1](https://arxiv.org/html/2604.07988v1)
- Table 1 explains why classical fault-tolerance methods break for agents:
  - Write-ahead logs (WAL) assume "Structured txns with schema + undo/redo", but agent actions "are arbitrary lambdas; no schema".
  - State machine replication (SMR) assumes a "Full, isolated state copy; deterministic execution", but agents act "on external environment; non-deterministic".
  - Checkpointing assumes local, deterministic state, but the "External environment [is] not checkpointable".
  - Durable workflows (Temporal, Restate) assume "Predefined control flow; explicit compensating actions", but agents have "Open-ended control flow (LLM-driven); no predefined undo".
  - The caption says "None addresses agentic safety." — [LogAct §2, Table 1](https://arxiv.org/html/2604.07988v1)

**Components**
- AgentBus: a linearizable, durable, append-only log, one per agent. It has typed entries (mail, inference input and output, intention, vote, commit/abort, result, policy), a blocking `poll`, and access control at the level of entry types. — [LogAct §3](https://arxiv.org/html/2604.07988v1)
- The state machine runs Inferring → Voting → Deciding → Executing:
  - The Driver runs inference and appends an intention.
  - Voters append votes.
  - The Decider appends commit or abort according to a quorum policy, such as `on_by_default`, `first_voter`, `boolean_OR` or AND.
  - The Executor runs the committed intention and appends the result. An abort returns control to the Driver.
  — [LogAct §3](https://arxiv.org/html/2604.07988v1)
- Voters come in two kinds. Classic voters use rules, static analysis or simulators and "offer hard guarantees for well-defined properties". LLM voters cover properties that are hard to specify. "LogAct mixes both types of components via quorums, allowing new implementations to be plugged in without downtime." — [LogAct §1](https://arxiv.org/html/2604.07988v1)
- Recovery differs by component:
  - Driver, Decider and Voters are classic replicated state machines that recover from a snapshot plus the log. Because inference outputs are logged, Driver "replay can be perfectly deterministic despite the non-determinism of the LLM".
  - A new Driver fences the old one by appending a driver policy entry.
  - The Executor is not replicated: "Executor recovery has to be conservative and aim for at-most-once execution." On reboot, "it appends a special entry of the result type to the AgentBus. This entry is picked up by the Driver; which relays it to the LLM; which responds with new intentions to examine the bus, inspect the environment, and potentially undo/redo actions. These intentions go through the Voters…"
  — [LogAct §3.2](https://arxiv.org/html/2604.07988v1)
- Semantic recovery means the agent determines "the lambda it was executing at the time of the crash; generate[s] and execute[s] exploratory lambdas to determine the state of the surrounding environment… and issue[s] compensating actions to either roll forward or roll back." — [LogAct §1](https://arxiv.org/html/2604.07988v1)
- Safety analysis (§3.1) separates three cases of a misbehaving Executor:
  - Case 1: it modifies the environment.
  - Case 2: it modifies itself, which breaks consistency between the log and the environment.
  - Case 3: it modifies the Voters or Decider. This is the worst case, and isolated infrastructure with different identities prevents it.
  — [LogAct §3.1](https://arxiv.org/html/2604.07988v1)
- Implementations (§4):
  - AgentBus backends: in-memory, SQLite, and a disaggregated store on DynamoDB or the in-house "AnonDB".
  - AgentKernel control plane with Raw, Auto-Decider, Auto-Voter and Spawn modes; Spawn runs sub-agents on K8s or as local processes.
  - Three harnesses. Claude Code is a "dirty-slate" integration: "We modify closed-source Claude Code using pre-execution hooks so that it logs to an AgentBus and waits for a voter response." AnonHarness is an internal CodeAct-style harness. LogClaw is a clean-slate Rust implementation and the only one where Driver and Executor are decoupled.
  — [LogAct §4](https://arxiv.org/html/2604.07988v1)

**Evaluation results (§5)**
- Overhead (§5.1), on a "hello world" C task (write, compile, run): inference dominates latency. The log grows by about 80 KB in 30 s, of which about 70 KB is the system prompt. — [LogAct §5.1](https://arxiv.org/html/2604.07988v1)
- Safety on AgentDojo (§5.2), with an older "Target" model:

  | Configuration | Benign utility | Attack success rate (ASR) | Avg. latency |
  |---|---|---|---|
  | Target, no defense | 81.4% | 48.2% | 6.7 s |
  | Rule-based voter | 49.5% | 1.4% | 10.6 s |
  | Rule-based + LLM voter (`boolean_OR`) | 78.4% | 1.4% | 12.2 s |
  | FrontierModel reference | 91.8% | 0% | 13.3 s |

  The rules were generated "by having an offline LLM look at the Target runs". The 1.4% of attacks that still succeed are "action-less". The LLM voter acts as an override that reads "the original user request… action outputs containing possible prompt injections, and also the vote of the rule-based voter". Voters were hot-swapped at runtime (at 312 s and 655 s in Fig. 7). — [LogAct §5.2](https://arxiv.org/html/2604.07988v1)
- Semantic recovery (§5.3) on a task to checksum 2,000 folders:
  - The 8th run exceeded a 3-minute timeout. A recovery agent was told to "inspect only the intentions on the original bus; redo the last intention (ideally without repeating work); but fix any obvious reasons that might cause a slowdown".
  - It spent 31 s on introspection and found the pathological `sorted(rglob(...))`. It then "locally tests" an `os.scandir()` replacement and finished the remaining 816 folders in 0.36 s ("290X faster"). The slow worker had processed 1,184 folders in about 155 s before it was killed.
  — [LogAct §5.3](https://arxiv.org/html/2604.07988v1)
- Swarm (§5.4): one coordinator and six sub-agents added type annotations to a large Python codebase.
  - Setup: in Base mode, agents coordinate by mailbox, for example to claim work. In Supervisor mode, an extra agent "periodically inspects the AgentBuses of the agents; and sends them mail".
  - Result: the Supervisor configuration did 17% more work with 41% fewer tokens. It spread fixes for infrastructure problems such as building code and finding CLIs, and it prevented duplicate type-fixing of the same files.
  - On gossip: "we found a Supervisor to be more effective than a decentralized gossip mode; agents typically did not stick to prompt-driven gossip protocols as their context windows got flooded by task information."
  — [LogAct §5.4](https://arxiv.org/html/2604.07988v1)

**Limitations and future work (verbatim)**
- "LogAct has its limitations. Inference (and hence, introspection) can be arbitrary and difficult to test due to the large input / output space. As a result, it is difficult to offer a binary guarantee that semantic recovery will restore the system to a clean state; or that an LLM-based voter will always catch an unsafe action." — [LogAct §1](https://arxiv.org/html/2604.07988v1)
- "Case 1 is inherently difficult to prevent, unless we have completely infallible Voters; practically, we expect testing and monitoring to ensure that Enforced-Safety never deviates hugely from Safety." — [LogAct §3.1](https://arxiv.org/html/2604.07988v1)
- "In practice, enforcing the exclusivity assumption (i.e., that a single LogAct agent operates exclusively on the environment) requires some form of concurrency control between agents… Further, we also need voters to determine that agents have followed such protocols before executing an intention. In this paper, we focus on the single-agent case, leaving the detailed exploration of multi-agent coordination protocols to future work." — [LogAct §3.1 "Concurrency"](https://arxiv.org/html/2604.07988v1)
- "Note that with external actions, Voters cannot base their vote on the environment, since it can change before the intention executes." — [LogAct §3.1](https://arxiv.org/html/2604.07988v1)
- "As noted earlier, LLM-based Voters do not get access to the environment; if such access is required for better votes, it carries the risk of prompt injection if they observe state written by the Executor." — [LogAct §3.1](https://arxiv.org/html/2604.07988v1)
- Conclusion: "LogAct is a first step towards ensuring that all agentic activity is visible, stoppable, and recoverable, paving the road for agentic systems that can provide strong guarantees in real-world settings." — [LogAct §7](https://arxiv.org/html/2604.07988v1)

**Coverage of the requested topics** (checked by keyword search of the full text for retry/retri, loop, test, undo, rollback, multi-agent and git)
- Retries and retry loops: none. Every "loop" hit refers to the ReAct/CodeAct "imperative loop" that LogAct replaces. — [LogAct full text](https://arxiv.org/html/2604.07988v1)
- Repeated failures: none. The failures studied are crashes, timeouts, a slow implementation and prompt-injected actions. — [LogAct](https://arxiv.org/html/2604.07988v1)
- Tests and test-driven coding: none, beyond the recovery agent that "locally tests" its fix (§5.3). In the paper, "test case" refers to AgentDojo cases. — [LogAct](https://arxiv.org/html/2604.07988v1)
- Multi-agent: the paper sketches mailbox coordination and agents inspecting each other's logs to "detect redundant or conflicting work, and dynamically re-partition tasks". The only evaluation is the §5.4 supervisor swarm. Protocols are deferred to future work. — [LogAct §1, §3.1, §5.4](https://arxiv.org/html/2604.07988v1)
- Related work (§6) covers only shared logs (CORFU, Tango, Delos and others), agentic safety (CaMeL, LlamaFirewall, Llama Guard) and Byzantine auditing (PeerReview, A2M, TrInc). Temporal and Restate appear only in §2. LangGraph, OpenHands and other agent-checkpoint frameworks are not cited. — [LogAct §2, §6](https://arxiv.org/html/2604.07988v1)

### Inferences
- LogAct's voters judge whether an intended action is safe *before it runs*. They never judge whether an outcome or failure is real, or whose fault it is. The log captures everything needed for attribution (intentions, results, inference I/O), but the paper uses introspection over that log only for recovery, health checks and supervision.
- The paper's own framing puts coding agents on git outside its hard case, because git already gives a transactional, sandboxed environment. So LogAct's main value proposition (durable intent and recovery for external side effects) adds little for code rollback in a SWE-bench-style loop. What it could add there is the voter and log structure itself: an auditable record of each attempt plus pluggable approval of risky actions, such as editing test files.
- The §5.4 result is the closest evidence that log introspection helps with repeated failures: a supervisor reading the logs stopped agents from each rediscovering the same infrastructure fixes. It is weak evidence (one task, two configurations, no variance reported).

### Gaps
- PDF text could not be extracted locally (no pdftotext or pypdf). The HTML v1 was used and should be identical.
- The paper reports no variance or repetition counts for §5.3 or §5.4, and the AgentDojo target model and FrontierModel are anonymized.
- No citing papers or follow-ups were found as of Nov 2026 (search: `"LogAct" agents cites OR follow-up AgentBus voters 2026`). Google Scholar citations were not checked.

## Q2. Which prior or concurrent works offer rollback or event sourcing for agents, and what gap is left for coding agents where git already provides code rollback?

### Takeaway
Checkpoint, replay and event-sourcing are standard by 2026: LangGraph checkpoints and time travel, the OpenHands SDK event log, Temporal's durable execution for the OpenAI Agents SDK, and a wave of 2025–2026 "transactional agent" papers. All of them restore *state* or settle *side effects*. None that I found treats the log as evidence for deciding *why* an attempt failed. For coding agents, git already covers code rollback, so the remaining gap is semantic: recognizing that a failure existed before the agent started, that a retry repeats an earlier failed approach, or that a test edit is legitimate.

### Cited Findings

**Framework mechanisms**
- LangGraph time travel:
  - Replay restarts from a checkpoint and "re-executes nodes—it doesn't just read from cache".
  - Re-executed side effects repeat: "LLM calls, API requests, and interrupts fire again and may return different results."
  - Forking does not roll back: "update_state does not roll back a thread. It creates a new checkpoint that branches from the specified point." "The original execution history remains intact."
  — [LangGraph docs: time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- OpenHands Software Agent SDK (arXiv 2511.03690, Nov 2025): the descriptions below come from search-result snippets of the paper, which I did not fetch directly.
  - It uses an event-sourcing pattern in which ConversationState is the only mutable component and holds an append-only event log of MessageEvent, ActionEvent, ObservationEvent and AgentErrorEvent.
  - Conversations can be resumed by loading the base state and replaying events, a "deterministic replay" design.
  — [OpenHands SDK paper, arXiv HTML](https://arxiv.org/html/2511.03690v1); [secondary: DEV guide](https://dev.to/truongpx396/openhands-deep-dive-build-your-own-guide-1al0)
  - The original OpenHands paper (arXiv 2407.16741, ICLR 2025) mentions "coordination between multiple agents" in its abstract. The abstract page does not describe the event stream. — [arXiv 2407.16741](https://arxiv.org/abs/2407.16741)
- Temporal + OpenAI Agents SDK: public preview July 2025, generally available on 23 Mar 2026. Durable execution retries failed model and tool calls and keeps state across crashes. InfoQ reported a community concern that the abstractions can hide control flow. — [Temporal blog](https://temporal.io/blog/announcing-openai-agents-sdk-integration); [PyPI temporalio-openai-agents](https://pypi.org/project/temporalio-openai-agents/); [InfoQ](https://www.infoq.com/news/2025/09/temporal-aiagent)
- LogAct's critique of durable workflows: they "require the developer to define the workflow's control flow graph upfront, including explicit compensating actions for each step", while agents have open-ended control flow and no predefined undo. — [LogAct §2](https://arxiv.org/html/2604.07988v1)

**Transactional, ACID and rollback papers, 2025–2026** (abstracts checked unless noted otherwise)
- Atomix (arXiv 2602.14849; v1 16 Feb 2026, v2 29 May 2026), "progress-aware transactions":
  - The runtime records each transaction's reads and effects, seals the transaction, and commits only when per-resource frontiers show no earlier conflicting work can still arrive. On abort, unreleased effects are suppressed and reversible ones compensated.
  - It argues that "retries, checkpoint replay, locks, and compensation" each blur which effects must settle together.
  — [arXiv 2602.14849](https://arxiv.org/abs/2602.14849)
- Agentic Transaction: Towards ACID-Compliant Agent Systems (Sun, Wang and Li; arXiv 2608.13900, 14 Aug 2026; cs.DB).
  - It defines "semantic" ACID, with transactional exploration-execution-validation cycles, "confidence divergence-based validation" and dependency-aware isolation.
  - It reports a 10.6% gain over state-of-the-art agents, including Claude Code. It describes a single data agent.
  — [arXiv 2608.13900](https://arxiv.org/abs/2608.13900)
- AgentRewind (arXiv 2608.14380, 14 Aug 2026) restores both agent context and environment to an earlier checkpoint and introduces MettleBench, a benchmark of "long-horizon engineering assignments". The abstract does not mention git or tests. — [arXiv 2608.14380](https://arxiv.org/abs/2608.14380)
- Rollback the World, Keep the Reflection (arXiv 2609.18304; v1 16 Sep 2026, v3 22 Sep 2026) rolls the environment back to a chosen earlier state but carries reflection on the abandoned path forward, to "avoid repeating past mistakes". The abstract does not mention coding, git or tests. — [arXiv 2609.18304](https://arxiv.org/abs/2609.18304)
- Safe to Resume? (arXiv 2608.29381, 29 Aug 2026) is a security paper showing that rollback and resume can break execution continuity. It runs end-to-end attacks on Hermes, Cline and LangGraph, including malware-verification bypass, unauthorized mail forwarding and double payment, and evaluates five frameworks in total. — [arXiv 2608.29381](https://arxiv.org/abs/2608.29381)
- Earlier work, seen in search results only and not fetched:
  - SagaLLM (arXiv 2503.11951): Saga-pattern transactions for multi-agent workflows, with a separate validation agent. — [arXiv 2503.11951](https://arxiv.org/pdf/2503.11951)
  - ALAS (arXiv 2505.12501 and 2511.03094): transactional multi-agent planning with logged compensation. — [arXiv 2511.03094](https://arxiv.org/pdf/2511.03094)
  - GA-Rollback (arXiv 2503.02519): an assistant LLM that triggers stepwise rollback. — [arXiv 2503.02519](https://arxiv.org/html/2503.02519)
  - ChronoMem (arXiv 2607.27773): version control for agent memory. — [arXiv 2607.27773](https://arxiv.org/pdf/2607.27773)

### Inferences
- Coding agents get file-level rollback "for free" from git and the sandbox, which LogAct itself concedes. LangGraph-, OpenHands- and Temporal-style replay adds rollback of agent *state* (conversation and graph state), not code.
- The gap for a test-driven retry loop is in attribution and memory across attempts, not in undo. "Rollback the World, Keep the Reflection" is the nearest neighbor: it keeps knowledge across rollbacks so mistakes are not repeated, but it is not coding-specific.
- "Safe to Resume?" suggests a caution for any design that replays or resumes from a log: resuming can re-trigger checks or side effects in unsafe ways.

### Gaps
- I did not read full texts of Atomix, Agentic Transaction, AgentRewind, Rollback-Induced Reflection or SagaLLM. Their claims come from abstracts only.
- The OpenHands SDK's event-sourcing details were not checked against the repository, and the SDK paper itself was not fetched.
- I did not search systems venues (OSDI, SOSP, NSDI, EuroSys, CIDR 2025–2026) directly for peer-reviewed versions. All the papers above are arXiv preprints.

## Q3. Does anything extend voters or shared logs to multi-agent coordination, or use a log or voter structure to decide "this failure is pre-existing" or "this test change is legitimate"?

### Takeaway
I found no system, paper or framework that uses a shared log or voter quorum to decide whether a failure was pre-existing, or whether a test modification is legitimate. LogAct names multi-agent coordination, and voters that check agents follow coordination protocols, as future work. Its only multi-agent result is a log-reading supervisor. Detecting test edits exists in reward-hacking benchmarks, which use hash or diff checks plus LLM judges, but these run as offline audits rather than as voters in the loop. The "verify pre-existing against main" check appears only in practitioner writing.

### Cited Findings

**Multi-agent coordination**
- LogAct proposes that "Multiple agents operating on a shared environment can coordinate via mailbox messages on each other's AgentBuses", and that agents can "detect redundant or conflicting work". It also states "we also need voters to determine that agents have followed such protocols before executing an intention", which it leaves as future work. — [LogAct §1, §3.1](https://arxiv.org/html/2604.07988v1)
- Other multi-agent work coordinates through shared state or voting, but not through a shared log or a decision about whether a failure is real:
  - DeLM: a shared verified context plus a task queue. — [arXiv 2606.10662](https://arxiv.org/html/2606.10662v1)
  - DecentLLMs: leaderless, Byzantine-robust selection in which evaluator agents score worker answers. — [arXiv 2507.14928](https://arxiv.org/html/2507.14928v1)
  - Insider attacks on multi-agent consensus. — [arXiv 2605.08268](https://arxiv.org/pdf/2605.08268)
  - A 2026 survey covering collaboration, failure attribution and self-evolution in multi-agent systems; seen in search only, not fetched. — [arXiv 2605.14892](https://arxiv.org/pdf/2605.14892)
- Related agent-safety work cited by LogAct: CaMeL (dual-LLM separation) and LlamaFirewall, which "proposes the use of pluggable safety verifiers; however, it does not describe a full system design for realizing this idea". — [LogAct §6](https://arxiv.org/html/2604.07988v1)

**Pre-existing failures**
- A practitioner post argues an agent should not call a failure "pre-existing" from memory. Instead it should check out main, run the failing test and compare the error. A matching error confirms the failure is pre-existing, while a different error or a pass on main means the change caused it. — [DEV: "When the agent calls the failing test 'pre-existing' and merges anyway"](https://dev.to/jeff_pdc/when-the-agent-calls-the-failing-test-pre-existing-and-merges-anyway-4me8)
- A GitHub issue on a project running concurrent agents describes transient test flakes caused by resource contention rather than regressions. The suggested check: "re-run the same failing test, alone, once contention clears." — [GitHub issue #984](https://github.com/remigiusz-antczak/deep-code-review/issues/984)
- TensorBench classifies failed coding-agent attempts by whether they "broke existing" tests. Qwen3 had 61 of 155 failures in "broke existing, no new tests", compared with 32 for Gemini 3.1 and 10 or fewer for every other agent. — [TensorBench, arXiv 2606.05570](https://arxiv.org/pdf/2606.05570)

**Test modification and reward hacking**
- EvilGenie flags "Modified Testing Procedure" reward hacking by comparing file hashes after the run, and finds LLM judges highly effective in unambiguous cases. — [EvilGenie, arXiv 2511.21654](https://arxiv.org/html/2511.21654v2); [evilgenie_inspect repo](https://github.com/JonathanGabor/evilgenie_inspect)
- HackTrace gives its judge the original and final tests, an AST comparison of the two and the execution outcomes. Exact-category agreement between the judge and labels was 78.5%; most confusions were between "evaluation bypass" and "test tampering". — [HackTrace, arXiv 2610.03055](https://arxiv.org/html/2610.03055v1)
- One 2026 paper counts any test-file modification as reward hacking "regardless of whether the submitted solution is subsequently verified as correct". — summarized in search results for [arXiv 2609.28614](https://arxiv.org/pdf/2609.28614); not fetched directly
- SpecBench separates the validation tests the agent can see from held-out tests. In one case an agent scored 97% on validation tests and 0% on held-out tests by hashing test inputs. — [SpecBench, arXiv 2605.21384](https://arxiv.org/html/2605.21384v1)

**Searches run that found no log- or voter-based failure adjudication**
- `LogAct shared logs agent reliability Balakrishnan`
- `transactional LLM agent framework rollback undo arXiv 2025`
- `guardian agent voter approval multi-agent coding failure adjudication pre-existing test failures`
- `shared log multi-agent coordination LLM agents consensus voting arXiv 2026`
- `"LogAct" agents cites OR follow-up AgentBus voters 2026`
- `coding agent modifies tests legitimate test change detection verifier reward hacking judge`
- A keyword scan of the LogAct full text for test, retry, loop and git.

### Inferences
- There is an open design space: a LogAct-style voter whose input is the attempt log, deciding things such as "this failure matches the baseline run on unmodified code, so it is pre-existing" or "this test edit is consistent with the issue". The ingredients exist separately:
  - LogAct: history-aware LLM voters, mixing rule and LLM voters by quorum, and hot-swappable voters.
  - Practitioner practice: comparing failures against a baseline run on main.
  - Reward-hacking work: test-diff/AST context fed to a judge.
  I found no work that combines them.
- A classic, rule-based voter, such as "the failing test ID set is a subset of the baseline set, with matching error signatures", gives the hard guarantee LogAct attributes to classic voters. An LLM voter could override it for ambiguous cases, as in LogAct's AgentDojo `boolean_OR` design. LogAct's warning applies here too: LLM voters that read environment output are exposed to prompt injection and to the agent's own self-serving claims.

### Gaps
- No peer-reviewed or benchmarked system adjudicates pre-existing failures or legitimate test changes with logs or voters. This conclusion rests on the searches listed above and could miss industry tools such as proprietary CI agents.
- I did not directly search the "guardian agents" industry category or individual AgentDojo defense papers (other than the LogAct and CaMeL references). Coverage of approval and voter mechanisms beyond LogAct, CaMeL and LlamaFirewall is therefore thin.
