# Research log

Running notes for the Loop Runner research direction. Newest entries go at the bottom of each section.
Mark every claim as **verified** (we read the source or ran it), **unverified** (seen in a summary or another AI's
answer), or **ours** (our own inference).

## Research question (current)

Failure attribution in verify-and-retry coding agent loops: can an agent, or a team of agents, tell failures it
caused from failures it didn't (already-failing, flaky, environment, tests pinning old behaviour), and does that cut
wasted spend without letting real bugs through?

Full literature report: `reports/Failure attribution in agent retry loops.md`
(notes behind it: `research_notes/Failure attribution in agent retry loops/`).

## Log

### 2026-11-06

**Where the idea came from**
- Reading LogAct (Meta, arXiv 2604.07988, 9 Apr 2026). **Verified**: log-and-voter design; single-agent focus;
  multi-agent coordination left to future work; no retry loops or test-driven coding agents; treats a coding agent
  on git as the easy case for rollback.
- Our SWE-bench Verified pilot kept hitting failures that weren't the agent's fault (see Experiments).

**Literature review (deep research, ~60 searches, mostly 2025–2026 preprints)**
- Gap is in *integration and measurement*, not primitives. **Verified as far as searched**: no paper
  (a) tests agents on repos with already-failing tests, (b) stops retrying because remaining failures aren't the
  agent's and reports cost saved, or (c) gives a separate agent/voter authority over test edits.
- Closest work: Agentless (pre-change test baseline, used to rank patches); "Breaking, Stale, or Missing?"
  (arXiv 2605.06125: Claude Code/Codex below 50% F1 at spotting tests a change must update; excludes repos with
  unrelated failing tests); "Verifying the Verifiers" (ICLR 2026 workshop: weaker LLM judges over-blame the task).
- Cautions: UTBoost (ACL 2025) found SWE-bench's per-test statuses wrong in ~54% of Verified instances, so
  attribution needs test IDs *and* error signatures, with reruns. ImpossibleBench: LLM monitors catch only 42–65%
  of test cheating on SWE tasks, so test-edit authority needs deterministic checks first.
- Don't claim "first system to attribute failures". The defensible contribution is the measurements, plus a
  labelled set of SWE-bench Verified tests (already failing / flaky / must change / regression risk), which doesn't
  seem to exist.

**"Gap 2" (rollback + context) checked and rejected as a main direction**
- Another AI's answer claimed nobody combines environment rollback with rewinding the LLM context. **Wrong**:
  - "Rollback the World, Keep the Reflection" (arXiv 2609.18304, Sep 2026, Wuhan Univ. + Alibaba). **Verified**:
    restores environment and truncates context to a checkpoint, distils the abandoned attempt into a separate
    reflection memory, marks facts that depend on undone actions for re-verification. ALFWorld, ScienceWorld, GAIA
    (not coding). +3 to +6.6 points over Reflexion-style baselines.
  - AgentRewind (arXiv 2608.14380, Aug 2026). **Verified (abstract only)**: aligned checkpoints of agent context
    and environment; new MettleBench of long engineering tasks.
  - ESAA (arXiv 2602.23193, Feb 2026). **Verified**: event-sourced intentions + deterministic orchestrator;
    single-author design paper, two case studies, no benchmark.
  - **Unverified, don't cite yet**: "Execution Control Harness for Governed LLM-Based Code Generation",
    "A Deterministic Control Plane for LLM Coding Agents", "Fault-Tolerant Sandboxing for AI Coding Agents",
    "Durable Execution for AI Agents". No IDs given; not found yet.
- **Ours**: the two directions meet in coding, where rollback is cheap (git). Open question: *when* to roll back
  and *what to tell the agent* (which failures were its own).

**AI-generated "50-paper reading list" (pasted from another assistant): treat as unverified**
- Repeats known errors: LogAct as "multi-agent decentralized logs" (it's single-agent), and the four "Gap 2" papers
  we couldn't find, now with dates attached.
- Real but miscited (**ours**, from prior knowledge): Firecracker is Agache et al., NSDI 2020; Kreps' "The Log" is
  2013; the Outlines paper is Willard & Louf 2023.
- Titles not recognised, verify before citing: CoT-Balancing, Cognitive Graphs, DyMem, the AutoGPT failure study,
  "Landscape of Agentic Validation (2000+ papers)", "MyVMs are Faster than Yours", Semantic Compilation Firewalls,
  and the 2024–2025 entries on AST compilers, interleaved static analysis, cross-project repair, prompt-injection
  firewalls, ACID for agentic tools, and infrastructure red-teaming.
- About half the list (Raft, Bigtable, MapReduce, Dynamo, microVMs, WASM) is infrastructure, off the research
  question. Focused list instead: LogAct, Agentless, "Breaking, Stale, or Missing?", "Verifying the Verifiers",
  ImpossibleBench, UTBoost, RIR, AgentRewind, Olausson et al., Gao & Peng, plus SWE-bench and Reflexion.

## Experiments (SWE-bench Verified, 10 bugs, Sonnet 5.5, one run per bug unless noted)

| Date | Run | Solved | Cost | Notes |
|---|---|---|---|---|
| 2026-11-06 | Our loop, baseline | 7/10 | $2.02 | astropy-13398 alone $1.51 |
| 2026-11-06 | Claude Code, first pilot | 7/10 | $0.30 | **Invalid**: a denied command made it stop running tests on ≥7 bugs |
| 2026-11-06 | Claude Code, fixed prompt (`42dfedf`) | 8/10 | $0.37 | Ran tests on 9/10; solved pytest-10356 |
| 2026-11-06 | Loop + stop on already-failing only (`b3313df`) | 7/10 | $2.02 | Rule never fired on astropy: spend is inside attempts |
| 2026-11-06 | Loop + name old failures before attempt 1 (`c4984a9`), astropy-13398 only | 0/1 | $0.54 | Was $1.51. Attempt 1 broke 5 tests; attempts 2–4 made no edits |
| 2026-11-07 | Same (`c4984a9`), all 10 bugs | 7/10 (same bugs) | $1.14 | −44% vs baseline; $0.16 per solve vs Claude Code $0.05. astropy-13398 $0.66 (same broke-then-no-edit pattern); sympy-15809 $0.17, still blocked by locked tests |

**Observed failure modes worth naming in a paper**
1. Retrying against a test that fails even with the gold patch (astropy-13398).
2. Correct fix rejected because locked existing tests pin old behaviour (sympy-15809: our diff = gold code change;
   `test_Min`/`test_Max` assert the old `ValueError`; SWE-bench's hidden test patch updates them).
3. Claude Code abandons verification after one denied shell command (fixed for the benchmark by telling it the
   test command is always allowed).
4. After being told about an old failure, the agent regresses other tests, then makes no-edit attempts.
   An empty diff looks like a cheap futility signal (**ours**; only weak prior evidence found).

**Decision gate: how common is the problem? (started 2026-11-06)**
- Worry: benchmarks filter out broken tests, so reviewers may say "this rarely happens". Our 10-bug pilot hit it 2/10.
- Measurement (`backend/benchmarks/swe_label.py`, commit `8117309`, no API cost): 60 random Verified bugs
  (seed 2026, pilot bugs excluded), visible tests run 3× on the original code and 3× with the official fix.
  Labels: already failing, must change, flaky, fixed by the official fix; plus whether the official fix resolves
  and whether the visible tests name files the hidden patch creates.
- Validated on known cases: astropy-13398 → `test_icrs_cirs` already failing; sympy-15809 → `test_Min`,
  `test_Max` must change.
- Gate (**ours**): ~10%+ of bugs affected → worth a paper and this is the dataset; ~1% → keep as a product fix only.
- Output: `/Volumes/LoopRunnerDocker/swe/labels.jsonl`, log `label.log`.

## Open questions / to do
- Is astropy-13398 one of the five Verified instances reported failing with the gold patch (SWE-bench GitHub #267)?
- Check the failing-test parser against more frameworks before relying on it (UTBoost warning).
- Find or rule out the four unverified "Gap 2" papers by title.
- Read AgentRewind's full text: how does it treat retained context, and is MettleBench coding?
- Design the labelled test set (run each instance's tests 5+ times on base and gold).

## Appendix: AI-suggested reading lists (unverified)

Lists suggested by other AI assistants, kept as given. Status: **ok** = real and correctly cited, as far as we know;
**miscited** = real but details wrong; **not found** = we searched and couldn't find it; **check** = not yet
verified (titles we don't recognise). Don't cite anything here until it's marked ok.

### List 1: "50 foundational papers" (pasted 2026-11-06)

**Group 1: Agent state systems, memory and event sourcing**

| # | Title as given | Status |
|---|---|---|
| 1 | ESAA: Event Sourcing for Autonomous Agents in LLM-Based Software Engineering (2026) | ok (arXiv 2602.23193) |
| 2 | LogAct: Enabling Agentic Reliability via Shared Logs (2026) | ok, but described wrongly: single-agent, multi-agent left to future work |
| 3 | A Deterministic Control Plane for LLM Coding Agents (2026) | not found |
| 4 | Durable Execution for AI Agents: A Design Pattern for Fault-Tolerant Execution (2025) | not found |
| 5 | Generative Agents: Interactive Simulacra of Human Behavior (Park et al., 2023) | ok |
| 6 | MemoryBank: Enhancing Large Language Models with Long-Term Memory (Li et al., 2023) | check (we know MemoryBank as Zhong et al., 2023) |
| 7 | MemGPT: Towards LLMs as Operating Systems (Packer et al., 2023) | ok |
| 8 | CoT-Balancing: Optimizing Context Token Efficiency in Stateful Agent Loops (2025) | check |
| 9 | Cognitive Graphs: Graph-Based State Management for Multi-Agent Planning (2024) | check |
| 10 | DyMem: Dynamic Memory Splicing for LLM Agent Rollbacks (2025) | check (suspicious: matches the disproved "Gap 2" claim) |
| 11 | Voyager: An Open-Ended Embodied Agent with Large Language Models (Wang et al., 2023) | ok (subtitle given wrongly as "with Automatic Curriculum") |
| 12 | AutoGPT: An Empirical Study of Autonomous Agent Failures in the Wild (2024) | check |
| 13 | Reflexion: Language Agents with Verbal Reinforcement Learning (Shinn et al., 2023) | ok |
| 14 | The Landscape of Agentic Validation: A Systematic Review of 2000+ Papers (2025) | check |

**Group 2: Repository mapping, compilers and execution control**

| # | Title as given | Status |
|---|---|---|
| 15 | RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph (2024) | ok |
| 16 | Execution Control Harness for Governed LLM-Based Code Generation (2026) | not found |
| 17 | SWE-bench: Can Language Models Resolve Real-World GitHub Issues? (Jimenez et al., 2023) | ok |
| 18 | RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems (2023) | ok (first author Liu, not Zhang) |
| 19 | Outlines: Fast and Deterministic Structured Generation (Louf & Fox, 2023) | miscited: "Efficient Guided Generation for Large Language Models", Willard & Louf, 2023 |
| 20 | CodePlan: Repository-Level Planning for Automated Code Editing (2024) | ok (Bairi et al., FSE 2024) |
| 21 | Tree-sitter architecture specification | ok (documentation, not a paper) |
| 22 | Abstract Syntax Trees in AI Development: A Multi-Language Compiler Approach (2024) | check |
| 23 | Aider: context compression via repository maps (Gauthier, 2024) | ok (blog post, not a paper) |
| 24 | Interleaved Static Analysis: Merging Linters into Agent Reasoning Engines (2025) | check |
| 25 | Automated Repair of Modern Software Ecosystems via Cross-Project Dependency Mapping (2025) | check |
| 26 | Semantic Compilation Firewalls for Non-Deterministic Codespaces (2026) | check |

**Group 3: Sandboxing, isolation and safety gateways**

| # | Title as given | Status |
|---|---|---|
| 27 | Fault-Tolerant Sandboxing for AI Coding Agents (2025) | not found |
| 28 | Firecracker: Lightweight Virtualization for Serverless Applications (2020) | miscited: Agache et al., NSDI 2020 |
| 29 | MyVMs are Faster than Yours: Micro-Second MicroVM Snapshotting (2024) | check |
| 30 | E2B infrastructure design whitepaper (2024) | check |
| 31 | Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations (Inan et al., 2023) | ok (subtitle given wrongly) |
| 32 | Prompt Injection Firewalls: Architectural Mitigations at the Gateway Layer (2024) | check |
| 33 | Deep dive into gVisor and Kata Containers (2022) | check (both projects real; this document unknown) |
| 34 | ACID Properties for Agentic Tools: Ensuring State Idempotency (2025) | check |
| 35 | Wasmtime runtime specification | ok (documentation) |
| 36 | Adversarial Red-Teaming of Infrastructure-Aware AI Agents (2025) | check |
| 37 | WitnessAI architecture (2024) | check (company real; document unknown) |
| 38 | Guaranteed JSON Schema Enforcement via Finite State Machines (2024) | check |

**Group 4: Classic distributed systems**

| # | Title as given | Status |
|---|---|---|
| 39 | Designing Data-Intensive Applications (Kleppmann) | ok (book) |
| 40 | The Log: What every software engineer should know... (Kreps, 2011) | miscited: 2013 |
| 41 | Time, Clocks, and the Ordering of Events in a Distributed System (Lamport, 1978) | ok |
| 42 | In Search of an Understandable Consensus Algorithm (Ongaro & Ousterhout, 2014) | ok |
| 43 | Actors: A Model of Concurrent Computation in Distributed Systems (Agha, 1986) | ok (title given loosely) |
| 44 | Dynamo: Amazon's Highly Available Key-value Store (DeCandia et al., 2007) | ok |
| 45 | Bigtable: A Distributed Storage System for Structured Data (Chang et al., 2006) | ok |
| 46 | MapReduce: Simplified Data Processing on Large Clusters (Dean & Ghemawat, 2004) | ok |
| 47 | Kafka: a Distributed Messaging System for Log Processing (Kreps et al., 2011) | ok |
| 48 | RESP protocol specification (Redis) | ok (documentation) |
| 49 | Consistent Hashing and Random Trees (Karger et al., 1997) | ok |
| 50 | End-to-End Arguments in System Design (Saltzer, Reed & Clark, 1984) | ok |

"ok" for items 5–50 comes from prior knowledge, not a fresh check. Groups 3–4 are mostly off the research question.
