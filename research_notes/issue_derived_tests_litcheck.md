# Literature check: issue-derived tests as the stop signal (checked 2026-11-07)

Method: web search plus arXiv abstract/HTML fetches. "Verified" means I read the number on the arXiv abstract or HTML page. "Snippet" means it came from a search-result summary and I did not read it on the primary page. Anything else is marked UNVERIFIED.

## 1. Confirmed papers

"F2P" = fail-to-pass rate: the test fails on the buggy code and passes with the gold patch.

| Paper | Authors / venue / ID / date | F2P result (model) | Notes |
|---|---|---|---|
| SWT-Bench: Testing and Validating Real-World Bug-Fixes with Code Agents | Mündler, Müller, He, Vechev. NeurIPS 2024 (the paper is in the NeurIPS proceedings). arXiv 2406.12952, Jun 2024, v3 Feb 2025 | SWT-Bench-Lite with GPT-4 (1106): SWE-Agent+ 18.5%, SWE-Agent 15.9%, LIBRO 14.1%, Aider 12.7%, AutoCodeRover 9.1%, ZeroShot 3.6% (verified, Table 2) | Using generated tests to filter SWE-Agent's patches "more than doubles" its precision, to 47.8%, at about 20% recall. That is patch filtering, not a stop signal. |
| TDD-Bench Verified: Can LLMs Generate Tests for Issues Before They Get Resolved? | Ahmed, Hirzel, Pan, Shinnar, Sinha (IBM). arXiv 2412.02883, 3 Dec 2024. No venue listed | Best model GPT-4o at 23.6% (snippet, from the intro, not seen in the tables) | 449 issues taken from SWE-bench Verified (verified). Proposes Auto-TDD. |
| Otter: Generating Tests from Issues to Validate SWE Patches | Ahmed et al. (IBM). ICML 2025. arXiv 2502.05368, v2 May 2025 | TDD-Bench-Verified with GPT-4o: Otter 31.4%, Otter++ (5-way ensemble) 37.0%. With Mistral-large: 26.9% / 32.1% (verified, HTML) | Filtering patches on the SWE-bench Verified leaderboard gives 65–92% precision at 30–41% recall across 22 systems. For the #3 system, precision rose from 60.8% to 91.9%. Cost is about $0.09 per instance. |
| Issue2Test: Generating Reproducing Test Cases from Issue Reports | Nashid, Bouzenia, Pradel, Mesbah. arXiv 2503.16320, v1 Mar 2025, v4 Jan 2026. No venue listed | 32.9% on SWT-bench-Lite (v4); v1 said 30.4%. The model is not named in the abstract (UNVERIFIED) | Refines tests until the failure *matches the issue's described symptom*, which is an assertion-semantics check and not just "it fails". Together, the compared tools reproduce 60.4%. |
| UTBoost: Rigorous Evaluation of Coding Agents on SWE-Bench | Yu, Zhu, He, Kang. ACL 2025 (long, pp. 3762–3774). arXiv 2506.09289 | Not an F2P generator: it augments tests | See Q4 |
| Agentless: Demystifying LLM-based Software Engineering Agents | Xia, Deng, Dunn, Zhang. arXiv 2407.01489, v2 Oct 2024. Venue UNVERIFIED (often cited as FSE 2025) | Not reported as an F2P rate | The abstract (32.0% on Lite) does not mention reproduction tests. Secondary sources (SWE-RL 2502.18449, TestPrune 2510.18270) describe the later version: it generates reproduction tests from the issue, keeps the majority-voted one, and ranks about 40 candidate patches by reproduction test result plus the fewest regression failures. This is **selection among candidates**, not a stop signal. |

## 2. Newer work (2025–2026, all real arXiv entries)

- **AssertFlip**, from Khatib, Mathews and Nagappan (arXiv 2507.17542, Jul 2025, v2 Jan 2026), reaches 43.6% F2P on SWT-Bench-Verified. It generates a test that *passes* on the buggy code, then flips the assertion.
- **e-Otter++**, from Ahmed, Ganhotra, Shinnar and Hirzel (arXiv 2508.06365, ICSE 2026), averages 63% F2P on TDD-Bench Verified. The v1 abstract also reports 52.5% on SWT-bench Lite (snippet). It uses heterogeneous prompting and execution feedback, and selects among tests.
- **BRT Agent at Google**, from Cheng et al. (arXiv 2502.01821, Feb 2025), produces plausible bug-reproduction tests for 28% of 80 internal bugs, against 10% for LIBRO. Giving these tests to the repair system yields 30% more plausible fixes (v1, snippet). The follow-up, **Dynamic Cogeneration of BRT** (arXiv 2601.19066, Jan 2026; FSE 2026 per a secondary index), has one agent write the fix and the test together, across 120 bugs. It covers at least as many bugs as the dedicated agent, and the test feeds the patch selectors, not a stop rule.
- **SWE-Tester**, from Soni et al. (arXiv 2601.13713, Jan 2026), fine-tunes open models on 41K instances. It gains up to +10 points absolute in success rate on SWT-Bench Verified.
- **ReProAgent**, from Zhang et al. (arXiv 2607.09123, Jul 2026), reproduces 58.43% on SWT-bench-Lite and 70.30% on SWT-bench-Verified, at $0.14 per instance.
- **DPIAgent**, from Liu et al. (arXiv 2608.23341, Aug 2026), reaches **81.76%** on SWT-Bench Verified with GPT-5, and 86.17% with test selection. This is the current top number I found.
- **TestPrune ("Can Old Tests Do New Tricks…")**, from Chen, Ahmed, Jabbarvand and Hirzel (arXiv 2510.18270, FSE 2026), minimizes regression tests. It gains 6.2–9.0% relative in reproduction and 8.0–12.9% relative in resolution in Agentless, SWE-Agent and Trae.
- **SWEPatchTest**, from Lu et al. (arXiv 2610.18004, Oct 2026), has 619 tasks and 82,579 agent patches. Its best configuration reproduces the bug on 59.29% of tasks, but its Joint Validation Rate (reproduce, accept correct patches, *and* reject wrong ones) is only **9.21%**. **This is the most important caution for our design.**
- **Agent-CoEvo ("Beyond Fixed Tests…")** (arXiv 2604.04580, Apr 2026) co-evolves populations of code and test patches. The figures 41.33% on SWE-bench Lite and 46.4% on SWT-Lite come from a third-party summary and are UNVERIFIED.

## 3. Q3: is "issue-derived test as STOP signal" new?

**Verdict: partially covered. The loop mechanism has been done. The combination with failure attribution and the false-alarm measurement appears open.**

Evidence that it is covered:
- **SpecRover** (Ruan, Zhang, Roychoudhury; ICSE 2025; arXiv 2408.02232) is the closest prior work. It has a reproducer agent and a *reviewer agent* that runs the reproducer on the original and patched code and judges **both** the test and the patch. A rejection is fed back to the patcher or the reproducer, and the loop continues. Once the reviewer approves, the regression suite runs, and a failure restarts the workflow (up to 3 times). The loop stops at "reviewer-approved and no regressions". Model: Claude 3.5 Sonnet. Reviewer precision was only **50.0%** on Lite (26 TP / 26 FP, 119 tasks). Tasks with a reproducer: 119/300. Resolution on Lite: 31.0%.
- **ExecCritic** (Tao et al., arXiv 2609.09133, Sep 2026) has a Test agent write tests, a fail-closed harness *qualify and freeze* them, and a Repair agent iterate without editing the tests. The test agent can **hurt**: base-model tests cut resolution from 61.2% to 57.3%, GPT-5.6 tests raised it to 65.3%, and the RL-trained pair reached 72.6%. Whether passing the frozen tests terminates the loop is not stated in the abstract (UNVERIFIED).
- **TDFlow** (Han et al., EACL 2026, arXiv 2510.23761) treats the task as "resolve these tests". With *human* tests it reaches 88.8% on Lite and 94.3% on Verified, with 7/800 test hacks. The authors conclude that **writing accurate reproduction tests is the bottleneck**.
- SWT-Bench, Otter, Agentless and Cogeneration all use generated tests for *filtering or selection*.

Evidence that the rest is open:
- I found no paper that separates **pre-existing or broken visible-test failures and stale tests that pin old behaviour** from agent-caused failures, and then uses "issue test passes and no previously-passing test breaks" as the stop condition. SpecRover's regression check does not say how it handles failures that were already present before the patch (UNVERIFIED in the full text).
- I found no measurement of how often a "visible tests green" stop rule triggers false-alarm retries, comparable to our 35% and 0/27 rescues.
- Adjacent work: **"Breaking, Stale, or Missing?"** (Shang et al., arXiv 2605.06125, May 2026; Defects4J) finds that agents identify stale tests with only about 36% F1 because they "rely on execution failure signals". **EET** (Findings of ACL 2026, arXiv 2601.05777) does early termination learned from past runs, cutting cost 19–55% with ≤0.2% resolution loss. It is not test-based.
- Counter-evidence to keep in view: **"Rethinking the Value of Agent-Generated Tests"** (Chen et al., arXiv 2602.07900, Feb 2026) finds on SWE-bench Verified that agent-written tests are only weakly linked to success, and that raising or lowering how many tests agents write does not significantly change outcomes.

## 4. Q4: generated tests that expose weak SWE-bench tests

- **UTBoost** found 36 instances with insufficient tests and 345 wrong patches labelled as passed. This changed 40.9% of Lite and 24.4% of Verified leaderboard entries (18 and 11 rank changes). A snippet gives 26 of the 36 as Verified instances. It also found parser errors in the harness.
- **PatchDiff ("Are 'Solved Issues'… Really Solved Correctly?")**, by Wang, Pradel and Liu (ICSE 2026, arXiv 2503.15223), differentiates 29.6% of plausible patches from the oracle patch. 7.8% of patches count as "correct" while failing the full developer test suite.
- **SWE-ABS**, by Yu et al. (arXiv 2603.00520, Feb 2026; ICML'26 per a secondary index), strengthens 50.2% of the 500 Verified instances. It rejects 19.71% of previously passing patches, and the top score falls from 78.80% to 62.20%.
- **OpenAI audit (23 Feb 2026, via Epoch AI's page):** 27.6% of Verified was audited, and 59.4% of the audited tasks had tests that reject *functionally correct* submissions. Epoch puts the floor at 16.4% of all tasks. OpenAI stopped reporting Verified. The often-quoted "35.5% overly strict" figure is UNVERIFIED because the OpenAI page returned 403.
- **Note:** all of these find tests that are too **weak**, except the OpenAI audit, which finds tests that are too **strict**. Our 17% "pins old behaviour" finding is the strict direction, so the OpenAI audit is the closest independent support for it.

## 5. Q5: separate test-writer and reviewer agents

- **AgentCoder** (arXiv 2312.13010) uses programmer, test-designer and executor agents. With GPT-4 it reaches 96.3% on HumanEval and 91.8% on MBPP. It covers function-level tasks only and has no repository or SWE-bench results.
- **SpecRover's reviewer** is the only repo-level test reviewer with a published precision figure (50%, see Q3).
- **ReProAgent** has a reflection tool. A "triadic review" appears only in a search snippet, not in the abstract (UNVERIFIED).
- **ExecCritic and Agent-CoEvo** separate the test role from the repair role, but neither has an LLM *critic of tests* (UNVERIFIED in the full text).
- **MASAI** has a test-template sub-agent (snippet only).
- No paper I found ablates "test reviewer on vs off" for F2P validity on SWE-bench.

## 6. Q6: failure modes of LLM-generated tests

- **Oracles follow the implementation, not the intent.** Konstantinou, Degiovanni and Papadakis (arXiv 2410.21136, Oct 2024) find that LLM oracles more often capture the *actual* behaviour than the expected behaviour, and are worse on buggy code.
- **Errors propagate from code to tests.** In Konstantinou, Tambon and Papadakis (arXiv 2607.05139, Jul 2026), tests written after faulty code catch 14% of faults against 25% for independently written tests. Code and tests "agree while both wrong".
- **Wrong code misleads the tester.** Huang et al. (arXiv 2409.09464) report test accuracy falling from about 80% to about 57% when the code under test is wrong (snippet).
- **A weak tester hurts the loop.** In ExecCritic, base-model tests reduced resolution by 3.9 points.
- **Reproduction is not validation.** SWEPatchTest finds 59% reproduction but 9% joint validation.
- **Test hacking.** TDFlow saw 7/800 hacks. In ImpossibleBench (Zhong, Raghunathan, Carlini; ICLR 2026; arXiv 2510.20270), GPT-5 cheats on 76% of oneoff-SWEbench tasks. Stronger models cheat more, and stricter prompts or restricted test access reduce cheating.

## What our angle would need to show to be new

1. **The false-alarm problem is measured and systematic.** About 35% of Verified tasks give a misleading visible-test signal even for the gold patch, and "all visible green" stopping wastes retries (0/27 rescued). Tie this to the OpenAI audit's strict-test finding.
2. **Stop-rule comparison with matched budget:** (a) all visible tests green, (b) issue test passes and no previously-passing test breaks (the baseline is recorded before any edit), and (c) SpecRover-style LLM reviewer acceptance. Report resolved rate, retries per resolved task, tokens, and false stops vs false retries. Being better than SpecRover's 50% reviewer precision is the bar.
3. **Robustness to bad issue tests:** run with gold-validated tests and with tests that are not oracle-validated. The fail-on-buggy check needs no gold patch; the pass-with-gold check is an oracle, so it must be removed or held out at deployment. Show that the stop signal survives realistic test-generation quality, around 40–80% F2P depending on the generator.
4. **Separating coder from tester.** Show reduced coder-tester collusion (independent context or a different model) and measure it in the way of 2607.05139.
5. **Disagreement flagging as an audit tool.** Report the precision of "issue test vs SWE-bench test disagreement" against a hand check, and compare with UTBoost and SWE-ABS (weak-test direction) and OpenAI (strict-test direction).
6. **Integrity.** Keep the 0/8 vs 4/8 ImpossibleBench-conflicting result, but n=8 is small. Expand it, and note that TDFlow and ImpossibleBench already study hacking.
