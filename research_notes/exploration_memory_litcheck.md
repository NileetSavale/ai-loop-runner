# Literature check: exploration-built, hash-invalidated repo memory for coding agents

Date: 2026-11-07. Method: web search + opening arXiv abstract pages (and full HTML where noted).
VERIFIED = I opened the abstract or paper page. UNVERIFIED = seen only in search snippets, or recalled.
Most verification is abstract-level only. Details marked "not stated" may be in the full paper.

## The idea (for reference)
A coding agent starts with no upfront index. The system records what agents explore, taken from their tool calls: search to file links, files read vs edited, tests that mattered, and short facts ("X is defined in Y"). This builds into a persistent per-repo graph or memory. Facts are keyed to file content hashes, so a code change invalidates them. Evaluation: same-repo SWE-bench tasks (for example about 24 Django bugs) run in chronological order, with memory vs without. Measures: exploration tokens and cost per task, solve rate, and whether cost falls as memory grows.

## Summary verdict: partly covered. One specific combination still looks open.

The field moved fast in 2026. These pieces are each already published:
- **Cross-task experience memory for SWE agents** is crowded: SWE-Exp, STAIR, Structurally Aligned Subtask Memory, SkillForge, AWM-style workflow induction. These store *strategies and lessons* distilled from trajectories. They do not store a structural map of the repo built from navigation.
- **Same-repo, history-ordered memory benchmarks** exist: SWE-Bench-CL (2025), SWE-ContextBench, ChainSWE, CL-Bench, VibeMemBench and MemDev-Bench (all 2026). So "run same-repo SWE-bench tasks in order, memory vs no memory" is **not novel as an evaluation protocol**. SWE-Bench-CL literally uses chronological per-repo sequences, including 50 Django tasks.
- **Persistent code graphs that cut tokens** exist, but they are built **upfront by static parsing**: Codebase-Memory, CodeNib, RepoGraph, LocAgent, CodexGraph, and products such as Cursor and codegraph.
- **Memory anchored to artifact content, with invalidation on drift** exists: EA-Graph (2026), and open-source tools such as agentmem and true-memory-fragments that store file or function hashes.
- **Navigation history as a recommendation signal** is old SE work: Mylyn/Mylar, NavTracks, Team Tracks (2005-2006).

**What appears open (hedged):** I found no paper that does all of the following together:
1. builds the repo knowledge structure *only* from agents' own exploration tool calls (search to file to edit to test links, plus typed facts), with no upfront static index;
2. keys those facts to file content hashes, so they are invalidated automatically as the repo evolves across a chronological task sequence;
3. reports **exploration tokens and dollar cost per task** as the main outcome, with a cost-vs-memory-size curve, next to solve rate.

The closest academic analogue is a 2005 human tool (NavTracks / Team Tracks), plus one 2026 blog post with no measurements. The novelty is in the *combination and the measurement*, not in any single primitive. That matches the repo's existing research framing.

Two warnings from recent results:
- VibeMemBench: 11 of 12 solver/memory-system pairs did not beat the no-memory baseline.
- CL-Bench: naive in-context learning beat dedicated memory systems.
- MemDev-Bench: unrelated memory causes regressions, and raw trajectories cut steps more than compressed memories do.

So a negative or null result is a real possibility. A design must be compared against a "raw prior trajectories" baseline, not only against no memory.

## Closest prior work (ranked by closeness)

1. **SWE-Bench-CL: Continual Learning for Coding Agents.** Joshi, Chowdhury, Uysal. arXiv 2507.00014 (June 2025). https://arxiv.org/abs/2507.00014. VERIFIED (abstract and full HTML).
   SWE-bench Verified tasks in chronological per-repo sequences: 8 repos, 273 tasks, Django has 50. FAISS memory of task summaries (problem, solution, rationale, tool usage).
   *Overlap:* almost exactly our evaluation protocol. *Differs:* memory is semantic summaries, not an exploration graph. No hash invalidation. "Tool-use efficiency" is time-based, and tokens are not measured. No memory-vs-no-memory agentic results were reported ("ongoing"). The harness result was memory "on par or slightly worse". **Must cite. We cannot claim the chronological same-repo protocol as new.**

2. **MemDev-Bench: Does Memory Help Code Agents?** Chen et al. arXiv 2610.27524 (Oct 2026). https://arxiv.org/abs/2610.27524. VERIFIED (abstract).
   555 base tasks, each with relevance-annotated earlier tasks from the same repo (4,869 historical tasks). Memory helps localization and editing. Unrelated history causes regressions. Raw trajectories cut steps more than compressed memories.
   *Differs:* benchmarks existing memory systems. Not an exploration-graph method. Reports steps, not tokens or dollars in the abstract. No invalidation.

3. **VibeMemBench.** Fan et al. arXiv 2609.23570 (Sep 2026). https://arxiv.org/abs/2609.23570. VERIFIED (abstract).
   111 targets from 90 SWE-rebench V2 repos, with 3,634 history trajectories. Injecting verified experience gives +1.1 to +4.5 pp and fewer steps. Four existing memory systems mostly fail to beat no memory.
   *Differs:* memory systems are generic. Not exploration-derived structure. No hash invalidation. Steps, not cost.

4. **SWE-ContextBench (SWE Context Bench).** Zhu et al. arXiv 2602.08316 (Feb 2026; v3 May 2026). https://arxiv.org/abs/2602.08316. VERIFIED (abstract).
   1,100 base + 376 related tasks linked by issue/PR dependencies. Well-summarized, correctly retrieved prior experience improves accuracy and **reduces runtime and token cost**.
   *Overlap:* measures token cost of experience reuse. *Differs:* related-task pairs, not a growing chronological memory. Reuses prior cases, not a navigation graph. No invalidation.

5. **CodeNib: A Multi-View Data System for Serving Repository Context to Coding Agents.** Yu et al. (incl. Jishen Zhao). arXiv 2607.25431 (Jul 2026). https://arxiv.org/abs/2607.25431. VERIFIED (abstract).
   Lexical, dense and structural views compiled per commit, reused across tasks, with incremental updates on change. Uses 50-87% fewer tokens than grep/read. 79 vs 66 resolved on 200 SWE-bench Verified tasks.
   *Overlap:* persistent reusable repo context, incremental updates on code change, token and cost measurement. *Differs:* **built upfront by static compilation**, not from agent exploration. Not learned over a task sequence.

6. **EA-Graph: Artifact-Anchored Verification Memory for Coding Agents under Upstream Drift.** Hsu, Chi, Everett. arXiv 2608.04278 (Aug 2026). https://arxiv.org/abs/2608.04278. VERIFIED (abstract).
   Cross-session memory of claims anchored to the artifact content that established them. Claims are classified unaffected, affected, or unprovable after drift. Tested on synthetic repos.
   *Overlap:* closest to our content-anchored invalidation. *Differs:* about verification claims, not navigation. Synthetic worlds. Explicitly makes no efficiency claim.

7. **Continual Learning Bench (CL-Bench).** Asawa et al. (incl. Zaharia, Gonzalez). arXiv 2606.05661 (Jun 2026). https://arxiv.org/abs/2606.05661. VERIFIED (abstract).
   Six domains including SWE, where "codebase layout" is the latent structure to discover online. Naive ICL beats dedicated memory systems.
   *Overlap:* explicitly frames learning the codebase layout across sequential issues. *Differs:* a benchmark, not a method. The abstract does not state token or cost metrics. A search snippet claimed per-repo blocks and fewer tool calls over time (UNVERIFIED).

8. **ChainSWE.** Jin et al. arXiv 2607.02606 (Jul 2026). https://arxiv.org/abs/2607.02606. VERIFIED (abstract).
   304 chronological, dependent issue chains across 54 Python projects. Performance drops up to 70% with chain length. A snippet mentions a "Seq+Mem" mode (UNVERIFIED).
   *Differs:* focuses on dependent fixes, where earlier patches change the code. Not an exploration-memory method. Relevant to the invalidation story.

9. **Practitioner analogue: "Giving my agent a map of the codebase (drawn partly from its own footsteps)".** Andre (olund), DEV Community, Jul 2026. https://dev.to/olund/giving-my-agent-a-map-of-the-codebase-drawn-partly-from-its-own-footsteps-1lm. VERIFIED.
   Logs agent reads, edits and writes into a co-touch matrix on top of a tree-sitter map. Hook-based re-parse plus periodic reindex.
   *Closest in spirit*, but it is a hybrid (upfront structural map plus behavioral layer), a blog post, and has **no measurements**.

## Repo-graph localization work (built upfront, per task or per commit)

| Work | Year / venue | Graph build | Persists across tasks? | Status |
|---|---|---|---|---|
| RepoGraph (Ouyang et al.), arXiv 2410.14684 | ICLR 2025 | Upfront static line-level graph, ego-graph retrieval | Per repo snapshot; no learning across tasks | VERIFIED (ICLR proceedings page in search) |
| CodexGraph (Liu et al., Alibaba), arXiv 2408.03910 | 2024 arXiv; NAACL 2025 per my recall (not confirmed) | Upfront static analysis into a graph DB | Index per repo; no learning | Existence VERIFIED; venue UNVERIFIED |
| LocAgent (Chen et al.), arXiv 2503.09089 | ACL 2025 (2025.acl-long.426) | Upfront heterogeneous graph (files, classes, functions; imports, calls, inheritance) | Index per repo snapshot; no learning | VERIFIED (ACL anthology) |
| OrcaLoca (Yu et al.), arXiv 2502.00350 | 2025; PDF header shows ICML template, venue not confirmed | Code graph plus priority-based action scheduling and distance-aware context pruning | Per task | Existence VERIFIED; venue UNVERIFIED |
| CoSIL, arXiv 2503.22424 | 2025 arXiv | **No pre-built index**: expands module then function call graph dynamically during search | Per task, discarded | VERIFIED (search snippets of arXiv HTML) |
| KGCompass, arXiv 2503.21710 | 2025 arXiv | Upfront repo-aware KG linking issues/PRs to code entities | Per issue | VERIFIED (snippets) |
| Agentless (Xia et al.), arXiv 2407.01489 | FSE 2025 per my recall | Hierarchical localization (file, class/function, line); no persistent graph | No | UNVERIFIED (recalled) |
| Codebase-Memory (Vogel et al.), arXiv 2603.27277 | 2026 arXiv | Persistent tree-sitter KG via MCP; about 10x fewer tokens, 83% vs 92% answer quality | Persistent, but upfront parse | VERIFIED (abstract) |

Contrast for our idea: CoSIL is the only one built lazily during search, but it is thrown away after each task. Every persistent graph here comes from upfront static parsing. None is built from accumulated agent navigation.

## Memory / experience work

- **Agent Workflow Memory (AWM).** Wang, Mao, Fried, Neubig. ICML 2025, arXiv 2409.07429. VERIFIED (proceedings listing). Induces reusable workflows from past trajectories (web agents: WebArena, Mind2Web). *Differs:* procedural workflows, web domain, no code structure, no invalidation.
- **ExpeL: LLM Agents Are Experiential Learners.** Zhao et al. AAAI 2024, arXiv 2308.10144. UNVERIFIED (recalled; search did not return it). Extracts natural-language insights and successful trajectories across tasks. Not coding-specific.
- **Reflexion.** Shinn et al. NeurIPS 2023. UNVERIFIED (recalled). Verbal self-reflection, mainly across retries of the same task, not across tasks.
- **SWE-Exp.** Chen et al. arXiv 2507.23361 (Jul 2025, rev. Feb 2026, no venue listed). VERIFIED (abstract). Experience bank of problem understanding, fault-localization patterns and modification strategies from past successes and failures. 73.0% on SWE-bench Verified with Claude 4 Sonnet. *Differs:* strategy-level experience; scope (cross-repo or same-repo) and cost not stated in the abstract.
- **STAIR (Reusing Past Repairs Through Hierarchical Trajectory Abstraction).** Xu, Zhou, Pan, Chen. arXiv 2607.29658 (Jul 2026). VERIFIED (abstract). Multi-level plan trees from past repair trajectories. 81.2% on SWE-bench Verified. Cost not stated.
- **Structurally Aligned Subtask-Level Memory for SWE Agents.** Shen et al. arXiv 2602.21611 (Feb 2026). VERIFIED (abstract). Memory stored and retrieved per subtask. +4.7 pp Pass@1 on SWE-bench Verified.
- **SkillForge: Self-Distilling Agents for Project-Specific Issue Resolution.** Chen et al. arXiv 2608.18933 (Aug 2026). VERIFIED (abstract). **Per-project, entity-grounded skills** distilled from synthetic issues it creates and solves. Explicitly motivated by "per-issue test-time exploration cost". *Close on the "per repo, cut exploration" goal.* *Differs:* proactive synthetic pre-training on the repo (an upfront phase), not passive accumulation from real tasks. Invalidation not addressed in the abstract.
- **Ontology-Grounded Project Memory (MOOSEDev).** James Adam. arXiv 2608.13662, NeSy 2026 Industry Track. VERIFIED (abstract). Typed KG of decisions, lessons and constraints with supersession links. Token cost about equal to a vector baseline. *Differs:* design knowledge, not navigation; supersession instead of hash invalidation.
- **Measure Before You Manage: Evaluating Agent Working Memory in Coding Agents.** arXiv 2608.31057 (2026). VERIFIED (abstract only, thin). A framework covering stored state, delivered context, management cost and outcome. A search snippet notes that content-equality guards are needed because version events do not prove semantic change (UNVERIFIED detail). Useful for metric design.
- **STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?** arXiv 2605.06527. UNVERIFIED (snippet only). A general benchmark for memory staleness.
- **BootstrapAgent.** arXiv 2605.15815. UNVERIFIED (snippet). Saves repo-setup exploration as a reusable contract. An adjacent "reuse exploration" idea, for environment setup.
- **Exploration Structure in LLM Agents for Multi-File Change Localization.** Fattha et al. arXiv 2606.11976. VERIFIED (abstract). Compares linear and parallel exploration on SWE-Bench Pro (ansible). A snippet said cross-issue note accumulation is listed as future work (UNVERIFIED; not in the abstract).
- **Cost-Effective Repository Exploration for Agentic Issue Localization.** Al Awad, Ivanov. arXiv 2608.29675. VERIFIED (abstract). Treats exploration as a separately budgeted stage. Cheap explorers keep 78-94% of Hit@3 with 84-95% fewer tokens. *Useful precedent for measuring "exploration tokens" as their own metric.* No cross-task persistence.
- **Token Reduction Is Not Cost Reduction.** arXiv 2607.12161. UNVERIFIED (snippet). Prompt caching discounts mean token savings may not turn into dollar savings. **Relevant: report dollars with cache accounting, not just tokens.**

## Sequential / continual SWE-bench evaluations
- SWE-Bench-CL (2507.00014): chronological per-repo sequences; Django 50 tasks. VERIFIED.
- ChainSWE (2607.02606): chronological dependent issue chains. VERIFIED.
- CL-Bench (2606.05661): sequential stateful domains, including SWE codebase layout. VERIFIED.
- MemDev-Bench (2610.27524) and VibeMemBench (2609.23570): same-repo history to later task. VERIFIED.
- SWE-ContextBench (2602.08316): related-task experience reuse with token cost. VERIFIED.

Takeaway: the protocol is established. Our contribution would have to be the *memory representation* (exploration-derived, hash-invalidated) and the *cost-curve measurement*, not the protocol.

## Older SE analogues (human navigation)
- **Mylar/Mylyn task context.** Kersten and Murphy, "Using Task Context to Improve Programmer Productivity", FSE 2006, DOI 10.1145/1181775.1181777. VERIFIED (bibliographic pages). A degree-of-interest model built from programmer interactions (selections and edits) and used to filter the IDE. SIGSOFT Impact Paper Award 2022. Per-task context, attachable to tasks and shareable. This is the human analogue of "files read vs edited".
- **NavTracks.** Singer, Elves, Storey, ICSM/IWPC 2005, pp. 325-334. VERIFIED (bibliographic plus PDF listing). Records developer navigation history and forms associations between files to recommend related files. **The closest human analogue to exploration-built file graphs.**
- **Team Tracks.** DeLine, Czerwinski, Robertson, "Easing Program Comprehension by Sharing Navigation Data", VL/HCC 2005, DOI 10.1109/VLHCC.2005.32. VERIFIED (MSR page in search). Shares a team's navigation patterns as "related items" and hides rarely visited code. The analogue of carrying memory across agents and tasks.
- Wear-based filtering and other history-mining work (for example, Zimmermann et al.'s ROSE co-change mining, ICSE 2004) belong to this family. UNVERIFIED (recalled, not searched).

## Industry tools (product docs; brief)
- **Cursor codebase indexing:** Merkle tree of file hashes for incremental re-index, and embeddings cached by chunk content (cursor.com/blog/secure-codebase-indexing). VERIFIED via search snippet of official blog. Hash-based invalidation, but an upfront embedding index, not exploration-built.
- **Claude Code memory (CLAUDE.md, auto-memory):** plain-text memory files the agent or user writes. No structural graph, no hash invalidation. UNVERIFIED (recalled product docs).
- **Devin Knowledge:** user and agent-suggested knowledge items retrieved per task. UNVERIFIED (recalled).
- **Sourcegraph / Cody:** upfront precise code-intelligence index (SCIP). UNVERIFIED (recalled).
- **Aider repo map:** tree-sitter plus PageRank map per session. UNVERIFIED (snippet).
- **OSS memory tools:** agentmem (file content hashes mark memories stale or changed), true-memory-fragments (git hooks plus blob and function hashes), codegraph (pre-indexed, auto-sync). VERIFIED only via search snippets of their READMEs. **They show that hash-keyed invalidation is already common engineering practice. Do not claim it as a novel primitive.**

## What we could defensibly claim vs must not claim

**Defensible (if the experiments support it):**
- "To our knowledge, no prior work builds a persistent repo memory *solely from coding agents' own exploration traces* and evaluates it on chronological same-repo SWE-bench sequences with exploration tokens and dollar cost as the main outcome." Hedge with "to our knowledge" and cite SWE-Bench-CL, CodeNib, EA-Graph and SkillForge as nearest.
- An empirical cost curve (per-task exploration tokens and dollars vs number of prior tasks and memory size), with cache-aware dollar accounting.
- A measured staleness rate: how many facts hash-invalidation removes over a real chronological sequence, and whether stale facts would have misled the agent. MemDev-Bench and ChainSWE suggest this matters, but neither measures it for this kind of memory.
- A comparison of exploration-built memory against (a) no memory, (b) raw prior trajectories (the MemDev-Bench finding), and (c) an upfront static index (CodeNib/RepoGraph-style). This is the comparison that would make the result meaningful.

**Must not claim:**
- That cross-task memory for SWE agents is new (SWE-Exp, STAIR, AWM, SkillForge and others).
- That chronological same-repo SWE-bench evaluation is new (SWE-Bench-CL, ChainSWE).
- That repo knowledge graphs for agents are new, or that they reduce tokens (Codebase-Memory, CodeNib, RepoGraph, LocAgent).
- That content-hash or artifact-anchored invalidation is new (EA-Graph, Cursor Merkle tree, agentmem).
- That learning from navigation history is new (NavTracks, Mylyn, Team Tracks).
- That memory reliably helps. Recent benchmarks (VibeMemBench, CL-Bench, SWE-Bench-CL harness results) found existing memory systems often fail to beat no memory.
- Generalization from about 24 Django tasks. That is one repo and a small n, so frame it as a case study unless it is extended to several repos (SWE-Bench-CL's 8-repo split is a ready-made extension).

## Sources
- SWE-Bench-CL: https://arxiv.org/abs/2507.00014 ; https://arxiv.org/html/2507.00014
- MemDev-Bench: https://arxiv.org/abs/2610.27524
- VibeMemBench: https://arxiv.org/abs/2609.23570
- SWE-ContextBench: https://arxiv.org/abs/2602.08316
- CodeNib: https://arxiv.org/abs/2607.25431
- EA-Graph: https://arxiv.org/abs/2608.04278
- CL-Bench: https://arxiv.org/abs/2606.05661
- ChainSWE: https://arxiv.org/abs/2607.02606
- Codebase-Memory: https://arxiv.org/abs/2603.27277
- SWE-Exp: https://arxiv.org/abs/2507.23361
- STAIR: https://arxiv.org/abs/2607.29658
- Structurally Aligned Subtask-Level Memory: https://arxiv.org/abs/2602.21611
- SkillForge: https://arxiv.org/abs/2608.18933
- Ontology-Grounded Project Memory: https://arxiv.org/abs/2608.13662
- Measure Before You Manage: https://arxiv.org/abs/2608.31057
- Exploration Structure (multi-file localization): https://arxiv.org/abs/2606.11976
- Cost-Effective Repository Exploration: https://arxiv.org/abs/2608.29675
- Token Reduction Is Not Cost Reduction: https://arxiv.org/pdf/2607.12161 (snippet only)
- STALE: https://arxiv.org/pdf/2605.06527 (snippet only)
- BootstrapAgent: https://arxiv.org/pdf/2605.15815 (snippet only)
- RepoGraph: https://arxiv.org/abs/2410.14684 ; https://proceedings.iclr.cc/paper_files/paper/2025/hash/4a4a3c197deac042461c677219efd36c-Abstract-Conference.html
- CodexGraph: https://arxiv.org/abs/2408.03910
- LocAgent: https://arxiv.org/abs/2503.09089 ; ACL 2025 long.426
- OrcaLoca: https://arxiv.org/abs/2502.00350
- CoSIL: https://arxiv.org/abs/2503.22424
- KGCompass: https://arxiv.org/abs/2503.21710
- Agent Workflow Memory: https://arxiv.org/abs/2409.07429 ; https://mlanthology.org/icml/2025/wang2025icml-agent
- Mylyn task context (FSE 2006): https://bibtex.github.io/FSE-2006-KerstenM.html ; https://www.cs.ubc.ca/news/2022/12/drs-gail-murphy-and-mik-kersten-receive-sigsoft-impact-paper-award
- NavTracks: https://www.st.cs.uni-saarland.de/edu/softmine2007/Papers/navtracks.pdf ; https://dblp.uni-trier.de/rec/conf/icsm/SingerES05.html
- Team Tracks: https://www.microsoft.com/en-us/research/?p=154634
- Practitioner post: https://dev.to/olund/giving-my-agent-a-map-of-the-codebase-drawn-partly-from-its-own-footsteps-1lm
- Cursor indexing (product blog): https://cursor.com/blog/secure-codebase-indexing
- OSS: https://github.com/virling/agentmem ; https://github.com/kyle641320/true-memory-fragments ; https://github.com/colbymchenry/codegraph
