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

## Experiments (SWE-bench Verified, 10 bugs, Sonnet 5.5, one run per bug unless noted)

| Date | Run | Solved | Cost | Notes |
|---|---|---|---|---|
| 2026-11-06 | Our loop, baseline | 7/10 | $2.02 | astropy-13398 alone $1.51 |
| 2026-11-06 | Claude Code, first pilot | 7/10 | $0.30 | **Invalid**: a denied command made it stop running tests on ≥7 bugs |
| 2026-11-06 | Claude Code, fixed prompt (`42dfedf`) | 8/10 | $0.37 | Ran tests on 9/10; solved pytest-10356 |
| 2026-11-06 | Loop + stop on already-failing only (`b3313df`) | 7/10 | $2.02 | Rule never fired on astropy: spend is inside attempts |
| 2026-11-06 | Loop + name old failures before attempt 1 (`c4984a9`), astropy-13398 only | 0/1 | $0.54 | Was $1.51. Attempt 1 broke 5 tests; attempts 2–4 made no edits |

**Observed failure modes worth naming in a paper**
1. Retrying against a test that fails even with the gold patch (astropy-13398).
2. Correct fix rejected because locked existing tests pin old behaviour (sympy-15809: our diff = gold code change;
   `test_Min`/`test_Max` assert the old `ValueError`; SWE-bench's hidden test patch updates them).
3. Claude Code abandons verification after one denied shell command (fixed for the benchmark by telling it the
   test command is always allowed).
4. After being told about an old failure, the agent regresses other tests, then makes no-edit attempts.
   An empty diff looks like a cheap futility signal (**ours**; only weak prior evidence found).

## Open questions / to do
- Is astropy-13398 one of the five Verified instances reported failing with the gold patch (SWE-bench GitHub #267)?
- Check the failing-test parser against more frameworks before relying on it (UTBoost warning).
- Find or rule out the four unverified "Gap 2" papers by title.
- Read AgentRewind's full text: how does it treat retained context, and is MettleBench coding?
- Design the labelled test set (run each instance's tests 5+ times on base and gold).
