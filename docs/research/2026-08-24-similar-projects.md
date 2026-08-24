# What PMOS Can Learn from Other Multi-Agent Project Orchestration Systems

**Date:** 2026-08-24
**Subject:** PMOS (`github.com/skadlem/pm-agent-team`) — portable multi-agent project-management template (roles in `roster.json`, wave execution with human gates, hybrid per-role KB, stable artifact IDs + RDF traceability, spend ledger, benchmark-driven model selection, protocol test harness).
**Method:** Primary sources only — official repos, official docs, and the papers. Every claim below carries its source URL. Where a popular approach is actually weak, or where PMOS already does better, it is called out explicitly. Working notes are kept alongside this report in `_notes/`.

---

## 0. Reading guide

Each project section answers the same eight questions:

1. **Role decomposition** — how roles/agents are defined and assigned work
2. **Context & knowledge sharing** — how agents share info, and how context is bounded
3. **Model assignment** — per-role model selection
4. **Cost management** — budget/cost guardrails
5. **Artifact handoffs & traceability** — formats, IDs, requirement-to-work links
6. **QA / verification / human gates**
7. **Failure handling** — retries, fallbacks, escalation
8. **Evaluation** — how the orchestration itself is measured

PMOS baseline (from its own `README.md`, `ORCHESTRATOR.md`, `EVALUATION.md`, read 2026-08-24): 10 roles with per-role model suggestions and fallback ladders; waves with GATE 1 (budget/model) and GATE 2 (scope/risk) human approvals; one SQLite hybrid KB per project (BM25+vectors, RRF fusion, 150K token cap, excerpts only); stable IDs R-/T-/A-/ADR-/L- with a deterministic linter and an RDF/SPARQL trace layer; `costs.jsonl` spend ledger with a budget cap; `recommend.py` benchmark-driven model selection (Epoch AI + LiveBench); `eval_project.py` fixture-based protocol harness. Known weak spots: paraphrase-retrieval MRR ~0.79; 300-line `ORCHESTRATOR.md` re-read in full every session; locked to one agent host's spawn/list-models/usage primitives.

---

## 1. MetaGPT — "the first AI software company" (SOP-encoded assembly line)

**What it is:** A multi-agent framework (70k stars) that encodes a software company's Standard Operating Procedures (SOPs) as a fixed pipeline — ProductManager → Architect → ProjectManager → Engineer → QA — run from one command: `metagpt "write a cli flappy bird game"`. Paper: *MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework*, ICLR 2024.
Sources: https://github.com/FoundationAgents/MetaGPT · https://arxiv.org/abs/2308.00352 · https://docs.deepwisdom.ai/main/en/guide/tutorials/multi_agent_101.html

1. **Roles:** Roles are Python classes (`Role` subclasses holding `Action`s). The SOP is expressed by wiring: each role `_watch`es specific upstream *Action message types* (e.g. coder watches `UserRequirement`, tester watches `WriteCode` output) and only reacts to those; the role loop is `_observe → _think → _act → publish_message` against a shared `Environment`. "Define each role… make each role observe the corresponding output from upstream, and publish its own for the downstream." Assignment is therefore *structural subscription*, not a free-for-all chat. https://docs.deepwisdom.ai/main/en/guide/tutorials/multi_agent_101.html
2. **Context:** A publish/subscribe **message pool** (the `Environment`) — messages are routed by `cause` (action type). Each role additionally keeps its own short-term `Memory`; long-term memory and an **experience pool** are optional (`role_zero` memory with `memory_k: 200` capacity and `similarity_top_k: 5` retrieval; `exp_pool` with BM25 or chroma retrieval plus an LLM reranker). The subscription mechanism *is* the context-boundary mechanism: a role only ever sees messages it watches, so the context is bounded structurally rather than by token math. https://raw.githubusercontent.com/geekan/MetaGPT/main/config/config2.example.yaml
3. **Models:** Per-role LLM configuration is first-class in `config2.example.yaml` (`roles: - role: ProductManager llm: … model: gpt-4-turbo-1106`, Architect on gpt-35-turbo, ProjectManager on Azure gpt-4, Engineer on gpt-35-turbo). This is the *declarative per-role model map* — the same idea as PMOS's `roster.json` + `team-model.json`, except the choice is hand-written, not computed from benchmarks. https://raw.githubusercontent.com/geekan/MetaGPT/main/config/config2.example.yaml
4. **Cost:** A `CostManager` tracks cumulative spend and the team raises `NoMoneyException` when `total_cost >= max_budget` — a hard stop on the whole team (default $10 in examples; logs show "Total running cost: $0.002 | Max budget: $10.000"). This is one of the earliest budget guardrails, but it is *crude*: a global cap with no per-wave estimation and no ledger, and it had known wiring bugs ("Set investment to 2, but the printed Max budget is 10"). PMOS's `cost.py` (per-role estimates, measured medians, exit-2 gating, failed-runs-recorded) is strictly stronger. https://github.com/geekan/MetaGPT/blob/main/metagpt/team.py · https://github.com/geekan/MetaGPT/issues/562 · https://github.com/geekan/MetaGPT/issues/1031
5. **Artifacts:** Structured documents — PRD, design doc, task list, then code — are the assembly-line intermediates, which the paper credits for cutting "cascading hallucinations" vs free-form chat. But artifacts have **no stable IDs and no requirement→code link** beyond prose; the workspace directory layout is the only trace. PMOS's R-NNN/T-NNN/A-NNN + RDF graph goes well beyond this.
6. **QA/gates:** The QA role writes and runs tests ("executable feedback"). Human gates are effectively absent in the default flow (a design decision — it is an autonomous framework, not a managed template).
7. **Failure:** `repair_llm_output` retries malformed JSON; LLM-call retries exist; `NoMoneyException` halts the team. There is **no per-role model fallback ladder** — PMOS's ladder (fresh worker on next model in role ladder, cap 4, then escalate) is ahead of MetaGPT.
8. **Evaluation:** The paper introduces the **SoftwareDev benchmark** (a set of small software tasks) evaluated on executability and pass rate, plus HumanEval/MBPP-style tasks; the repo also ships a SWE-bench runner. Evaluation targets the *end product*, not the orchestration process. https://arxiv.org/abs/2308.00352

**Skeptical note:** MetaGPT is the origin of "SOP as pipeline" and its structured-artifacts insight directly validates PMOS's wave/artifact design. But the pipeline is fixed (new flows require code), per-role models are hand-picked, the cost cap is a blunt axe, and development has slowed (core repo essentially stable since 2024). PMOS's config-driven roster + computed model selection + measured budget ledger are each an improvement over the original.

---

## 2. ChatDev — chat-chain waterfall (communicative dehallucination)

**What it is:** A 34k-star framework where phases (design/coding/testing/documenting) run as **dual-agent sub-chats** (instructor + assistant) along a "chat chain", with "communicative dehallucination" (the assistant asks the instructor for more detail instead of guessing). ChatDev 2.0 (Jan 2026) rebuilt it as a node/workflow graph engine ("Dev All") with MCP support, multi-provider models, and Mem0 memory. Paper: *ChatDev: Communicative Agents for Software Development*, ACL 2024.
Sources: https://github.com/OpenBMB/ChatDev · https://arxiv.org/abs/2307.07924

1. **Roles:** Role names + phase prompts live in JSON configs (ChatChainConfig / PhaseConfig / RoleConfig) — CEO, CPO, CTO, programmer, reviewer, tester, art designer. Assignment is a **fixed phase chain**; users compose custom chains. ChatDev 2.0 makes phases into nodes of an editable workflow graph with a schema registry.
2. **Context:** Each phase is a bounded dialogue; solutions are passed phase-to-phase as artifacts (the "chat chain"). 1.0 had no long-term memory; follow-up work added **Experiential Co-Learning** (an experience pool accumulated across tasks, arXiv:2312.17025) and **MacNet** (scaling multi-agent collaboration on graphs to 1000+ agents, arXiv:2406.07155). 2.0 integrates **Mem0** with per-user/per-agent scoping (commit log: "update Mem0Memory to use independent user/agent scoping"; the config exposes memory backends). https://github.com/OpenBMB/ChatDev · https://arxiv.org/abs/2312.17025
3. **Models:** 1.0 used one global model; 2.0 is multi-provider (OpenAI, DeepSeek, etc.) per node. No benchmark-based per-role selection — PMOS's `recommend.py` is unique in this field.
4. **Cost:** The paper reports per-software costs around a dollar and time-to-build as metrics — *measured for the paper, not enforced at runtime*. There are no runtime budget guardrails; PMOS's ledger + cap is stronger. https://arxiv.org/abs/2307.07924
5. **Artifacts:** Outputs land in a `WareHouse/<task>` directory (code + documentation). No stable IDs, no requirement→code traceability. PMOS's ID discipline is a real differentiator here.
6. **QA/gates:** A reviewer phase and tester phase review/execute; "self-improvement" passes are available; no mandatory human gate by default.
7. **Failure:** Dialogue-level retries; 2.0 strips leaked `<think>` tokens from reasoning models (a real production lesson for anyone running R1-class models); no model fallback ladder.
8. **Evaluation:** The paper evaluates on a small set of software tasks (three modalities) with **manual** assessment of executability/completeness and reported cost/time. No standing, reproducible harness; MacNet adds math/game benchmarks. This is exactly the weak spot PMOS's `eval_project.py` fixture harness addresses (deterministic, free, mutation-tested).

**Skeptical note:** ChatDev's evaluation is small and manual, and 1.0→2.0 was a full rewrite (a portability warning for anyone who builds on top of it). Its useful lessons for PMOS: (a) the "communicative dehallucination" pattern (worker may ask upstream for clarification instead of guessing) could map to PMOS's escalation rule, and (b) experience pools (co-learning, MacNet) are the closest thing the field has to "KB enrichment across projects" — PMOS's per-project KB enrichment is more disciplined, but a cross-project experience namespace is worth considering.

---

## 3. AutoGen → AG2 / Microsoft Agent Framework — conversation-based agent OS

**What it is:** AutoGen (Microsoft, 2023) popularized multi-agent *conversations* (AssistantAgent/UserProxyAgent, GroupChat). The project then fragmented: Microsoft moved on to **Microsoft Agent Framework** (MAF, the AutoGen + Semantic Kernel successor), while the community fork **AG2** ("the open-source AgentOS") continues independently. Both are frameworks, not SDLC templates.
Sources: https://github.com/ag2ai/ag2 · https://github.com/microsoft/agent-framework · https://docs.ag2.ai

1. **Roles:** Agents are code objects with a system message + tools. A `GroupChatManager` selects the next speaker (round-robin, LLM-based, or custom selector); "Swarm-style" **handoffs** let an agent transfer control explicitly. MAF formalizes graph workflows: sequential, concurrent, handoff, and group collaboration patterns. Assignment is dynamic and often LLM-decided — the opposite of PMOS's deterministic wave roster. https://github.com/ag2ai/ag2
2. **Context:** Conversation history is the shared state; AG2 provides middleware (TransformMessages) to bound it, a KnowledgeStore/RAG layer, a Memory interface, and OpenTelemetry telemetry. MAF adds checkpointing, thread-based durable execution, and "time travel". Context bounding is bolted on via middleware rather than designed in. https://github.com/ag2ai/ag2 (README "Knowledge & Memory", "Middleware", "Telemetry")
3. **Models:** Per-agent `llm_config` with a `config_list` of model/provider entries and `filter_dict` for selection; different agents can use different models. Ordering in the list acts as a manual fallback chain. No benchmark-driven selection, no per-role cost-tiering. PMOS's computed selection + ladder is strictly more advanced.
4. **Cost:** Usage/cost is reported (telemetry, `print_usage` lineage) but there is **no project budget guardrail** in the framework — you build your own. Magentic-One (same lineage, below) adds the interesting piece: a *progress ledger* rather than a dollar ledger.
5. **Artifacts:** Code execution in sandboxed executors; no artifact ID or requirement-linkage layer. Work products are files in a workspace, untracked semantically.
6. **QA/gates:** The famous pattern is `UserProxyAgent` with `human_input_mode=ALWAYS|TERMINATE|NEVER` — the human gate is a first-class knob, and termination conditions (message matching, max turns) gate loops. This is the cleanest "human-in-the-loop flag" in the field and maps directly to PMOS's GATE 1/2 stops.
7. **Failure:** `max_consecutive_auto_reply`, nested chats for error recovery, and human takeover are the mechanisms; MAF adds middleware exception handling. No model-ladder equivalent.
8. **Evaluation:** AG2 documents an Evaluation user-guide section, and Magentic-One ships **AutoGenBench** — a standalone harness with explicit *repetition and isolation* controls ("important when agents' actions have side-effects"). That isolation discipline is a lesson for PMOS's harness. https://arxiv.org/abs/2411.04468

**Skeptical note:** AutoGen's own history is the cautionary tale: a project with 100k+ stars got forked and successor-frameworked (AG2 vs MAF), leaving users to choose between lineages. It is also a *framework* — it will orchestrate any conversation you define, but gives you no project-management structure (no requirements, no gates, no budget, no traceability). PMOS occupies a genuinely different niche: a *managed SDLC template on top of* an agent host.

### 3a. Magentic-One — orchestrator + task/progress ledger

**What it is:** Microsoft's generalist multi-agent system (arXiv:2411.04468): one Orchestrator (lead) + four specialist agents (WebSurfer, FileSurfer, Coder, ComputerTerminal).
Sources: https://arxiv.org/abs/2411.04468

1. **Roles:** Orchestrator plans, delegates, tracks, re-plans; specialists are interchangeable modules — "agents can be added or removed from the team without additional prompt tuning or training".
2. **Context:** The key mechanism is the **Task Ledger** (facts, guesses, plan) and **Progress Ledger** (the orchestrator periodically answers self-reflection questions: *is the team making progress? is it looping? what should happen next?*). This is a compressed, explicit, machine-readable summary of "where are we" that survives context churn — conceptually what PMOS's `.pmos/` artifacts + `log.md` are, but *generated by the orchestrator as part of its loop* rather than by deterministic tooling.
3. **Models:** All agents share the same underlying LLM config in the reference implementation (no per-role tiering).
4. **Cost:** No dollar budget; instead **stall detection** — if progress stalls for a few cycles the orchestrator revises the ledger and re-plans (fresh plan rather than grinding).
5–6. **Artifacts/QA:** No SDLC artifacts; QA is delegated to the Coder's test execution; no human gates in the default loop.
7. **Failure:** The *re-plan on stall* mechanism is the standout: instead of retrying the same step, the orchestrator re-decomposes. PMOS's wave-4→wave-3 rework loop is a coarse version of this; a stall counter + "re-plan vs retry" decision would be a direct adoption.
8. **Evaluation:** Evaluated on **GAIA (38%)**, WebArena (32.8%), AssistantBench (27.7%) via AutoGenBench with repetition + isolation. This is the strongest example in the field of *shipping the harness with the system*.

---

## 4. CrewAI — role-play crews + flows, and the most evolved OSS memory

**What it is:** 57.5k-star framework: `Crew` (agents + tasks) for role-play pipelines, `Flow` for deterministic event-driven orchestration (`@start/@listen/@router` decorators, Pydantic state, persistence).
Sources: https://github.com/crewAIInc/crewAI · https://docs.crewai.com/en/concepts/memory

1. **Roles:** Declarative: `Agent(role=…, goal=…, backstory=…, tools=…, llm=…)`; crews are scaffolded from YAML (`agents.yaml`/`tasks.yaml`). Two processes: **sequential** (task order) and **hierarchical** (a manager LLM assigns work to agents dynamically). Flows add a deterministic state machine — closer to PMOS's wave model than the free-chat frameworks.
2. **Context/memory (the standout):** CrewAI v1.15 has a **unified `Memory`** system: hierarchical **scopes** (filesystem-like: `/project/alpha`, `/agent/researcher`), LLM-analyzed saves (infers scope/category/importance), and recall ranked by a **composite score = semantic (0.5) + recency (0.3) + importance (0.2)** with exponential recency decay (`recency_half_life_days`), plus consolidation of near-duplicate memories (>0.85 similarity) and adaptive-depth recall. With `memory=True`, a crew auto-extracts facts from each task output and injects recall into the next task prompt. Per-agent scoped views give privacy (`memory.scope("/agent/researcher")`). This is the field's most complete "shared memory with bounded injection" design. https://docs.crewai.com/en/concepts/memory
3. **Models:** Per-agent `llm` (any LiteLLM model string); defaults to the crew LLM. No automatic selection — PMOS is far ahead here.
4. **Cost:** No OSS budget guardrail (cost lives in telemetry/enterprise). Per-agent `max_iter`, `max_rpm` (rate limiting!), and per-task `max_execution_time` exist — the RPM/rate-limit knob is something PMOS lacks.
5. **Artifacts:** `Task.output_file` writes results to files; `context=[task…]` passes task outputs. **No stable IDs, no traceability** — PMOS's linter/RDF layer is strictly better.
6. **QA/gates:** Task **guardrails** (a validation function/agent that can reject output and trigger retry with feedback) and per-task `human_input=True` (block until a human answers). These are clean primitives; PMOS has the same ideas embedded in its protocol but not as reusable task-level flags.
7. **Failure:** Guardrail retry loops (with `max_retries`), `max_iter` "must produce final answer" enforcement, rate-limit backoff. No model fallback ladder.
8. **Evaluation:** No standard OSS evaluation — a notable gap for such a popular framework. (Enterprise AMP platform has evals; the OSS core doesn't.)

**Skeptical note:** CrewAI's memory is impressive but *expensive and non-deterministic*: every save runs an LLM analysis, and recall quality depends on the memory LLM. PMOS's deterministic chunk IDs + fixed token caps + BM25/vector fusion are cheaper and reproducible, and PMOS already enforces "excerpts only, never full dumps" (CrewAI injects whatever recall returns). What PMOS should steal: **recency/importance weighting in recall ranking** (PMOS's RRF has no time dimension), and the **scoped private/shared split** (PMOS has per-role namespaces but no per-worker private scratch).

---

## 5. AgentScope — observability + fault tolerance as first-class features

**What it is:** Alibaba's developer-centric platform (29.4k stars; v2.0.x active) — "agents you can see, understand, trust" — with a Studio UI for tracing, actor-based distributed runtime, and built-in fault tolerance. Papers: arXiv:2402.14034, arXiv:2508.16279.
Sources: https://github.com/agentscope-ai/agentscope · https://arxiv.org/abs/2402.14034

1. **Roles:** Agents are code (`ReActAgent` with system prompt + toolkit); composition via pipelines (sequential/conditional/loop) and a `MsgHub` for broadcast. No prescribed SDLC roles — it's an infrastructure framework.
2. **Context:** Message-based exchange with hub-based routing; per-agent memory; session persistence/history management (2.0). Context bounding is developer-managed.
3. **Models:** Per-agent model configs (JSON); an *automatic prompt-tuning mechanism* in the 1.0 paper. No benchmark-driven selection.
4. **Cost:** A "utility monitor" tracks usage/cost (visible in Studio); no budget cap.
5–6. **Artifacts/QA:** None SDLC-specific; the paper's emphasis is *robustness*: "built-in and customizable fault tolerance mechanisms" — rule-based correction, parse functions, retries.
7. **Failure:** This is AgentScope's core competence: retry with output parsers, custom fault handlers, service wrappers, actor-level resilience for distributed deployments. It's the most systematic treatment of *infrastructure-level* failure in the field (vs PMOS's *model-level* failure ladder — the two are complementary).
8. **Evaluation:** No orchestration benchmark; the 1.0 paper is feature-focused; the project leads with observability tooling rather than eval harnesses.

**Skeptical note:** AgentScope is a framework, not a project template — adopting it means building your own SDLC layer. Its lesson for PMOS is **observability**: tracing every message/decision is what makes an orchestration debuggable, and PMOS's `.pmos/log.md` + `costs.jsonl` could grow a structured wave-events trace to match (see Lessons §L-9).

---

## 6. CAMEL — role-playing societies and the Workforce failure-recovery engine

**What it is:** "The first and best multi-agent framework… finding the scaling law of agents" (17.6k stars). Started as role-playing (AI user ↔ AI assistant with inception prompting); now includes **Workforce**, a production-grade team engine, and **OWL**, an open-source deep-research agent that topped the GAIA leaderboard among open frameworks.
Sources: https://github.com/camel-ai/camel · https://docs.camel-ai.org/key_modules/workforce/

1. **Roles:** `Workforce(description, children, coordinator_agent, task_agent, new_worker_agent, …)`: a **coordinator assigns**, a **task agent decomposes**, and a **`new_worker_agent` dynamically creates new workers** on demand — dynamic team composition, unlike PMOS's fixed roster (PMOS's roster is justified by impact surface at launch; CAMEL can grow the team mid-task). Worker types: `SingleAgentWorker` (pooled via `AgentPool`) and `RolePlayingWorker` (two-agent debate).
2. **Context:** Structured Pydantic data exchange (`Task`, `TaskResult`, `TaskAssignment` with dependencies); optional `share_memory=True` for workers; `use_structured_output_handler` for reliable JSON/tool calls even on models without native tool-calling — a practical portability trick PMOS could note for host-agnostic spawns.
3. **Models:** Per-worker models via `ModelFactory` (e.g. a cheap model for creative workers) — per-role model assignment, hand-picked.
4. **Cost:** No dollar budget; but `task_timeout_seconds` and `graceful_shutdown_timeout` bound runaway work — timeouts are a cost guardrail PMOS lacks per worker.
5–6. **Artifacts/QA:** No SDLC traceability. Human-in-the-loop is a *tool*: agents call `HumanToolkit` (`ask_human_via_console`) — the human gate as an agent tool rather than an external protocol stop.
7. **Failure (the standout):** Workforce runs an explicit **failure analysis → `RecoveryDecision`** pipeline with a taxonomy: **retry** (with feedback), **replan**, or **decompose** the failed task differently. Callbacks observe lifecycle events and metrics. This is the most explicit failure-taxonomy in the field, and exactly what PMOS's binary "retry on next ladder model / escalate" could evolve into.
8. **Evaluation:** CAMEL's research arm benchmarks heavily (OWL on GAIA); the framework itself relies on external benchmarks rather than a built-in harness.

---

## 7. OpenHands — event streams, condensers, and the best context-bounding machinery

**What it is:** The leading open AI coding agent (84.9k stars) + a **Software Agent SDK** (agents, tools, conversations, workspaces; Agent Server; Agent Canvas UI; automation service). SWE-bench Verified ~77.6% on the SDK badge. Tech report arXiv:2511.03690.
Sources: https://github.com/OpenHands/OpenHands · https://github.com/OpenHands/software-agent-sdk · https://docs.openhands.dev/sdk/arch/condenser

1. **Roles:** Primarily a *single* CodeAct-style agent per conversation; "major tasks that involve multiple agents" are supported by composing agents/conversations in the SDK (the SDK ships `Agent`, `Conversation`, tools like `TaskTrackerTool`, `TerminalTool`, `FileEditorTool`). Repo-level "skills" (formerly microagents) inject project context. No SDLC role roster.
2. **Context (the standout):** The **Condenser system** is the field's most engineered context-bounding mechanism. It manages the conversation event log: `should_condense()` threshold detection (e.g. `max_size: 120` events), then keeps the *first N + last M* events, LLM-summarizes the middle into a `Condensation` event carrying `forgotten_event_ids`, and produces a view of ~half the limit. Concrete condensers: `NoOpCondenser`, `LLMSummarizingCondenser`, `PipelineCondenser` (multi-stage chains). The design principle — *compress the middle, keep the head and tail, record what was forgotten* — is directly applicable to PMOS's "protocol docs re-read every session" problem. https://docs.openhands.dev/sdk/arch/condenser
3. **Models:** Per-agent LLM config (any model string/base URL); no automatic selection.
4. **Cost:** `max_budget_per_task` (default `0.0` = *no limit* — the guardrail exists but is opt-in) and `max_iterations` (default 100). Session stats expose `accumulated_cost`. Lesson: even the best project ships cost caps off by default; PMOS's default-on $20 cap is a deliberate, stronger stance. https://docs.openhands.dev/openhands/usage/v0/advanced/V0_configuration-options
5. **Artifacts:** File edits + patches in a sandboxed workspace; `TaskTrackerTool` for task tracking; the event log is the trace. No requirement-ID linkage.
6. **QA/gates:** **Security analyzers** (LLM-based risk classification of actions, configurable policy, action confirmation) gate dangerous operations — a *per-action* gate, stronger than PMOS's wave-level gates for the code-writing phase. https://docs.openhands.dev/sdk/guides/security
7. **Failure:** Condensation on context overflow; agent-loop retries; delegation of subtasks. No model ladder.
8. **Evaluation:** SWE-bench Verified (77.6% badge), Terminal-Bench, GAIA, WebArena; the SDK README leads with a benchmark badge — evaluation as marketing, but grounded.

**Skeptical note:** OpenHands condenses *events*, not knowledge: the middle of a long session is summarized away and the detail is gone (hence `forgotten_event_ids`). PMOS avoids the problem architecturally (workers never accumulate long sessions; the KB is the durable store). OpenHands's answer to "long context" is compression; PMOS's is *prevention* — keep both in mind.

---

## 8. SWE-agent — the Agent-Computer Interface, and what simplicity looks like now

**What it is:** "Takes a GitHub issue and tries to automatically fix it" (20k stars; NeurIPS 2024). One agent, one repo, one loop. As of 2026 it is in **maintenance-only mode**, superseded by **mini-swe-agent** — a ~100-line agent with no special tools that is "simpler & more flexible while still being as performant".
Sources: https://github.com/SWE-agent/SWE-agent · https://arxiv.org/abs/2405.15793 · https://swe-agent.com/latest/usage/

1. **Roles:** None — deliberately. The paper's thesis is that the *interface* (ACI), not the number of agents, drives performance.
2. **Context:** The ACI is designed for context economy: a **windowed file viewer** (100-line windows, explicit scroll/goto commands), terse command surfaces, and `history_processors` that trim the observation stream. The paper shows that verbose interfaces can exhaust "an agent's cost budget or context window" and hurt performance — evidence that *context frugality is a performance lever, not just a cost lever*.
3. **Models:** Any LiteLLM-supported model via YAML config (`agent.model`), with template variants; no per-role logic (single agent).
4. **Cost:** LiteLLM tracks per-call cost; trajectories record spend. No enforcement cap; the paper frames cost-budget exhaustion as a failure mode the ACI must avoid.
5. **Artifacts:** A **trajectory is saved after every step** (`.traj`) — full audit trail of actions/observations, which is how the project does post-hoc analysis. Patches are the deliverable.
6. **QA/gates:** None internal (SWE-bench's hidden tests are the gate).
7. **Failure (well-engineered loop):** `forward_with_handling` catches and feeds back, in order: `FormatError` → re-inject a format-correction prompt (up to `max_requeries=3`), blocked actions → blocklist message, invalid bash → `bash -n` syntax pre-check, command timeouts → consecutive-timeout counter that eventually escalates. A *deterministic pre-flight validation of the agent's own output* before it hits the environment — the same philosophy as PMOS's `artifacts.py` linter, applied to shell commands. https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/agents.py
8. **Evaluation:** The project co-created **SWE-bench** (issue→PR gold-patch benchmark) and is measured on it (paper: 12.47% resolved on SWE-bench full, GPT-4, 2024-era); trajectories are published for independent analysis.

**Skeptical note:** The maintenance-mode handoff to mini-swe-agent is itself a lesson: the elaborate ACI toolkit was simplified away once models got better. PMOS should keep its protocol surface lean and re-validate every "process" feature against the current model generation — complexity that exists only to compensate for old models is debt.

---

## 9. Claude Code subagents + agent teams (and Anthropic's multi-agent research system)

**What it is:** Claude Code's built-in delegation model: **subagents** (in-session workers with their own context windows) and the newer **agent teams** (experimental; separate sessions that coordinate through a shared task list and direct messaging). Anthropic's engineering blog describes the same orchestrator-worker pattern in production.
Sources: https://code.claude.com/docs/en/sub-agents · https://code.claude.com/docs/en/agent-teams · https://www.anthropic.com/engineering/multi-agent-research-system

1. **Roles:** A subagent is a Markdown file with YAML frontmatter: `name`, `description`, `tools` (allow/deny), `model` (inherit/sonnet/opus/haiku). **Delegation is description-driven**: the main agent reads the `description` and decides when to spawn it. Built-ins include Explore (read-only; inherits the session model, capped at Opus; *skips CLAUDE.md* to stay fast/cheap) and Plan. Agent teams: the lead session spawns named teammates in natural language; teammates claim work from a **shared task list** and **message each other directly** — a genuinely different coordination topology (no funnel through the lead).
2. **Context:** Each subagent runs in "its own context window" and "returns only the summary" — compression by isolation. The docs are explicit that this preserves main-context space. The Anthropic blog's production pattern adds the **artifact pattern**: subagents write full results to a shared filesystem and return *lightweight references*; the lead never re-reads everything through chat returns. This is the strongest external validation of PMOS's "artifacts on disk + summaries in context" rule.
3. **Models:** The subagent `model` field is the per-role model assignment, and the docs' stated purpose includes cost: "Control costs by routing tasks to faster, cheaper models like Haiku." Anthropic's blog reports the lead on Opus 4 with Sonnet 4 subagents beating single-agent Opus 4 by **90.2%** on their internal research eval, and that *token spend was the strongest predictor of answer quality* — i.e. more parallel context (budget permitting) is the highest-leverage knob. PMOS's GATE-1 budget approval is the governance side of exactly this finding.
4. **Cost:** The blog quantifies the trade: multi-agent used ~15× the tokens of chat, with 2–3 months of tuning expected to stop over-spawning; docs note agent teams "use significantly more tokens than a single session". **Effort-scaling heuristics** in the orchestrator prompt (1 subagent for simple fact-finding, 2–4 for comparisons, 10+ for complex research) are the cost guardrail — a prompt-level rule rather than a ledger. PMOS's ledger is stronger mechanically; the *heuristic* is still worth adopting.
5. **Artifacts:** Files on disk + references; no requirement IDs. The blog's appendix: "implement artifact systems where specialized agents can create outputs that persist independently… then pass lightweight references back to the coordinator."
6. **QA/gates:** Hooks (e.g. a `PreToolUse` hook that blocks SQL writes and feeds the block message back) are deterministic guardrails at the tool level — comparable to PMOS's linter-before-done rule, but *enforced by the host*, which PMOS cannot currently do through jcode.
7. **Failure:** Docs acknowledge team limitations (session resumption, coordination, shutdown). When context limits approach, "agents can spawn fresh subagents with clean contexts while maintaining continuity through careful handoffs." No model ladder (the `model` field is fixed per subagent).
8. **Evaluation:** Anthropic uses **internal end-state evaluations**: a small set of research tasks with rubric grading of the final artifact plus ablations (lead-vs-single, model mixes). The 90.2% figure is internal, not a public benchmark — treat it as directional.

**Skeptical note:** Agent teams are experimental, and the synchronous-wave design stalls on the slowest subagent (acknowledged in the blog). PMOS's wave model has the same property; the fix (async waves) is listed as unsolved there too. Also note the host lock-in: subagent YAML works only inside Claude Code — the same portability trap PMOS has with jcode, which is why §L-10 proposes host adapters.

---

## 10. GitHub spec-kit — spec-driven development as a portable process (131k stars)

**What it is:** A toolkit that turns "define what to build before building it" into slash commands workable with **30+ AI coding agents** (Claude Code, Copilot, Codex, Cursor…): constitution → specify → clarify → plan → tasks → implement → converge. MIT; 1.0.0 in Aug 2026.
Sources: https://github.com/github/spec-kit (README)

1. **Roles:** No agent roster — it orchestrates *one* coding agent per run. But **bundles** package "role-oriented setups" (product manager, business analyst, security researcher, developer personas) as installable command sets, and **extensions/presets** add commands or re-template artifacts. The "team" is the process, not the agents.
2. **Context:** The **spec artifacts are the shared knowledge**: `constitution.md` (project governing principles, established once, "guide all subsequent development"), then per-feature `specs/NNN-<slug>/` with spec/plan/research/data-model/contracts/tasks. A template-resolution stack (project overrides > presets > extensions > core) lets organizations standardize artifact formats. This is "context as durable files" — same philosophy as PMOS's `.pmos/` markdown-as-source-of-truth.
3. **Models:** N/A (the host agent's model). No selection logic.
4. **Cost:** None.
5. **Artifacts (standout):** Tasks are numbered (`T001…`) with a `[P]` parallel marker and checkbox tracking; `/speckit.taskstoissues` **exports the task list to GitHub Issues** — the cleanest external-traceability bridge in this survey, and a natural complement to PMOS's T-NNN IDs. `/speckit.analyze` runs **cross-artifact consistency and coverage analysis** before implementation (an LLM analog of PMOS's deterministic linter — less reliable but catchier for semantic gaps). `/speckit.checklist` generates "quality checklists… like unit tests for English."
6. **QA/gates:** `/speckit.converge` assesses the codebase against spec/plan/tasks and **appends remaining work as new tasks; you repeat implement↔converge until it reports "Converged"** — a mechanical convergence loop. `/speckit.clarify` forces clarifying questions before planning.
7. **Failure:** No retry taxonomy; the loop is human-invoked.
8. **Evaluation:** None (community walkthroughs only) — it's a process toolkit, and it doesn't pretend otherwise.

**Skeptical note:** spec-kit's "analysis" and "converge" steps are prompt-driven, so they can be fooled the same way agents can — PMOS's deterministic `artifacts.py` + SPARQL checks are strictly more trustworthy for *structural* truth, while spec-kit's value is the *semantic* check (does the code actually do what the spec says), which PMOS's harness explicitly does not cover (EVALUATION.md: "says nothing about the quality of what agents write"). A combined design: PMOS determinism for structure + a spec-kit-style converge prompt for semantics.

### 10a. GitHub Agent HQ — the platform layer (context)
Announced Universe 2025: **mission control** to "assign, steer, and track the work of multiple agents" (Copilot, Claude, Codex, Jules…), **branch controls** for agent-created code, a **code-review step inside the Copilot coding agent before the human sees it**, `AGENTS.md` as versioned agent configuration, and an enterprise **control plane** for policy/audit. The pattern: agents work on *issues*, in *branches*, gated by *review* — the software-engineering process itself is the orchestration medium. https://github.blog/news-insights/company-news/welcome-home-agents/

---

## 11. Kiro (AWS) — the most productized spec-driven workflow

**What it is:** AWS's AI IDE whose headline feature is **Specs**: a three-phase, human-approved pipeline — `requirements.md` → `design.md` → `tasks.md` — stored under `.kiro/specs/<name>/`. Proprietary product (not open source), but the docs are public and the *pattern* is the lesson.
Sources: https://kiro.dev/docs/specs/ · https://kiro.dev/docs/specs/feature-specs/ · https://kiro.dev/docs/steering/

1. **Roles:** Single agent (custom agents exist as a feature); the *phases* are the structure.
2. **Context:** **Steering files** (`.kiro/steering/*.md`) are persistent project knowledge ("instead of explaining your conventions in every chat") with **inclusion modes: always / fileMatch / manual** — i.e. *conditional context injection*, the field's cleanest answer to "how much project doc do you load into context?" PMOS's KB search is retrieval-based; Kiro's `fileMatch` mode is rule-based gating that costs zero tokens when not matched.
3. **Models:** N/A (product-internal).
4. **Cost:** None exposed.
5. **Artifacts (standout):** Requirements use **EARS notation** (`WHEN <trigger> THE SYSTEM SHALL <response>`) — "structured, testable requirements" whose acceptance criteria cover edge cases; an explicit **"Analyze Requirements" step** catches "logical inconsistencies, ambiguities, conflicting constraints, and gaps" *before design*; and **Refine** propagates requirement edits down into design and tasks. PMOS's R-NNN/A-NNN already give the trace; EARS wording + a pre-GATE-2 requirements analysis would sharpen the content.
6. **QA/gates:** Approval is required between phases (Quick Spec exists for skipping gates when appropriate — an explicit "small change, skip the gates" knob, same spirit as PMOS's roster right-sizing); a task-execution UI tracks per-task status; a **Correctness** feature (property-based testing, IDE) is the QA add-on.
7. **Failure:** Manual iteration (edit requirements → Refine).
8. **Evaluation:** None public.

---

## 12. BMAD-METHOD — the closest analog to PMOS (agile AI-driven development template)

**What it is:** 52k-star open-source **method + skill/agent template** ("Breakthrough Method for Agile AI-Driven Development") that turns an idea into software with role agents (Analyst, PM, Architect, UX, Dev, QA, SM/PO as skills), while "the process sizes itself to the work" — small changes go straight to build; complex work gets planning. v6 = SKILL.md-based agents; modules include the core method, Test Architect (TEA), and **bmad-loop** (builds/verifies/retros an epic unattended).
Sources: https://github.com/bmad-code-org/bmad-method (README + commit history)

1. **Roles:** Agents are **skills** (SKILL.md with role definitions), invoked as needed rather than spawned as a fixed roster; workflows (bmad-build, bmad-review…) drive them. Three-layer customization (skill defaults → team → user) via TOML. Role assignment is emergent per workflow — unlike PMOS's launch-time roster.
2. **Context:** "Durable context — carry product and technical decisions forward instead of re-explaining them in every chat": briefs/specs/architecture docs are the memory; per-party append-only memlogs for session memory; **staged-diff handoffs** (review content staged once to a file, prompts reference the path instead of re-pasting diffs — token-frugal handoffs).
3. **Models:** Model-agnostic; the user's IDE model is used. No selection.
4. **Cost:** None.
5. **Artifacts (standout):** PRD/SPEC.md, DESIGN.md (+EXPERIENCE.md), epics/stories with acceptance criteria, sprint status as YAML; **sprint-planning opens with a readiness gate** that does "generic artifact discovery by content, **forward/back traceability, PASS/CONCERNS/FAIL, stop on FAIL**" — a human/agent gate fed by a deterministic script (`sprint_plan.py` with 11 tests) that does the mechanical parsing while "judgment stays with the LLM." That split — *deterministic tool for structure, LLM for judgment* — is exactly PMOS's `artifacts.py` philosophy, and BMAD industrializes it.
6. **QA/gates (standout):** bmad-build's review step is gated by an **"Fits AC?" acceptance check between Implement and Review**, with four review lenses: **Blind Hunter, Edge Case Hunter, Acceptance Criteria Audit, Verification Gap**; a **claims-falsification pass** forces the agent to back its claims with evidence (PMOS's verification-before-completion skill, systematized); `bmad-loop` runs the whole epic loop unattended including verification and retro.
7. **Failure:** Story-level rework loops; no model ladder.
8. **Evaluation:** A **deterministic skill validator** (`tools/validate-skills.js`, 13 rules, runs in under a second in CI, exits non-zero on HIGH findings) — the template validates *itself* in CI, like PMOS's `validate.py` (130 checks) and `eval_project.py`. No outcome-quality benchmarks.

**Skeptical note:** BMAD is heavier than PMOS (dozens of skills, plugin marketplaces, modules) and has no model selection or cost governance at all — PMOS's GATE-1/ledger/ladder are the missing piece in BMAD. But BMAD is the strongest evidence that a *plain-markdown, agent-host-agnostic template* (its skills run in Claude Code, Cursor, Gemini, etc.) is a viable distribution model — directly relevant to PMOS's jcode lock-in question.

---

## 13. Extras seen while surveying (brief)

- **Roo Code custom modes** (IDE): per-mode YAML (role definition, tool groups, file permissions, `whenToUse` routing hints) + **sticky model per mode** (the tool remembers which model you last used for each role) + an **Orchestrator "boomerang" mode** that decomposes work and routes subtasks to modes. Cheap, practical per-role model routing with zero benchmark machinery. https://docs.roocode.com/features/custom-modes
- **AgentVerse** (OpenBMB, ICLR 2024): research framework whose task-solving pipeline is *expert recruitment → collaborative decision-making → action → evaluation*; agents are **recruited per task and dismissed when done** (dynamic team sizing). Mostly dormant; evaluation research-oriented (MATH, software-dev tasks). https://github.com/OpenBMB/AgentVerse
- **Agent evaluation literature** (Langfuse, MLflow, Cameron Wolfe's guide): the field's consensus is to evaluate at three levels — final output, **trajectory** (what the agent did), and **single step** (why it failed) — and to separate capability evals from regression evals. PMOS's harness covers protocol-level decisions deterministically; trajectory-level eval is the open gap. (https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation, https://mlflow.org/articles/ai-agent-evaluations-a-developers-practical-guide/, https://cameronrwolfe.substack.com/p/agent-evals)

---

## 14. Cross-project synthesis

### 14.1 Where the field agrees (patterns that recur everywhere)

1. **Artifacts-on-disk is the universal memory.** Every system that works at project scale converges on files as the durable shared state: MetaGPT's PRDs, ChatDev's WareHouse, spec-kit's `specs/`, Kiro's `.kiro/specs/`, BMAD's docs, Anthropic's filesystem artifacts, PMOS's `.pmos/`. Chat histories are ephemeral; files are the contract. PMOS's choice of markdown-as-source-of-truth is the mainstream answer.
2. **Role decomposition = per-role prompts + bounded inputs.** From MetaGPT's `_watch` subscriptions to Claude Code's subagent descriptions to CrewAI's role/goal/backstory: a role is a system prompt plus a *restricted* view of shared state. The restriction (subscription, tool allowlist, scope) is what makes it a role.
3. **Context bounding is now the headline engineering problem** — condensers (OpenHands), windowed viewers (SWE-agent), scopes (CrewAI), inclusion modes (Kiro), "own context window, return the summary" (Claude Code), artifact references (Anthropic). Nobody dumps everything anymore. PMOS's "excerpts only, hard caps, never full dumps" is squarely on-pattern.
4. **Deterministic checks where you can, LLM judgment where you must.** BMAD's script cores + PASS/CONCERNS/FAIL gates, SWE-agent's format/syntax pre-checks, spec-kit's task numbering, PMOS's linter. The best systems push structure into code and keep prose for judgment.
5. **Human gates are either first-class or the product dies.** AutoGen's `human_input_mode`, CrewAI's `human_input=True`, Kiro's phase approvals, BMAD's gates, Agent HQ's review step. Autonomous-only pipelines (MetaGPT/ChatDev defaults) are demos or research.
6. **Benchmarks gate *agents*, not *orchestration*.** SWE-bench, GAIA, WebArena, Terminal-Bench measure end-task success. Only PMOS (and, thinly, MetaGPT's SoftwareDev) measures the *process* — and only PMOS does it deterministically without spending tokens.
7. **The 2024→2026 trajectory is simplification.** SWE-agent → mini-swe-agent (maintenance mode), MetaGPT/ChatDev/AgentVerse plateaued, BMAD v6 simplified its workflow language, spec-kit converged on fewer commands. Elaborate orchestration that only compensates for old models is being deleted.

### 14.2 Where they diverge (and what the divergence means)

| Dimension | Divergence | Implication for PMOS |
|---|---|---|
| Team structure | Fixed pipeline (MetaGPT/ChatDev) vs dynamic (CAMEL recruits workers, AgentVerse recruits/dismisses, Claude teams spawn on demand) vs deterministic roster (PMOS/BMAD) | Roster-by-impact-surface is defensible; consider *optional* mid-project recruitment (CAMEL `new_worker_agent`) |
| Speaker/assignment control | LLM-decided (AutoGen GroupChat, CrewAI hierarchical) vs pre-wired (PMOS waves, MetaGPT SOP) | LLM-decided assignment is flexible but non-reproducible; PMOS's determinism is a feature for gates/audit |
| Memory model | Event compression (OpenHands), LLM-analyzed facts (CrewAI), retrieval (PMOS), files (spec-kit/Kiro/BMAD) | These compose, not compete; PMOS lacks the *time* dimension (recency) and *per-worker scratch* scoping |
| Cost | Ledger+cap (PMOS, MetaGPT) vs progress ledger (Magentic-One) vs prompt heuristics (Anthropic) vs nothing (most) | PMOS leads; add stall detection + per-worker timeout + effort heuristics |
| Failure | Model ladder (PMOS), retry/replan/decompose (CAMEL), re-plan-on-stall (Magentic-One), deterministic pre-checks (SWE-agent) | PMOS's ladder is unique and good; the taxonomy should widen beyond "model failed" |
| Host coupling | Framework-native (AutoGen/AgentScope/OpenHands) vs host-agnostic template (spec-kit 30+ integrations, BMAD, PMOS) | PMOS is host-agnostic in spirit but jcode-locked in practice — the biggest gap |
| Eval of the system | Deterministic protocol harness (PMOS, BMAD's validator), end-task benchmarks (OpenHands/SWE-agent/Magentic-One), internal rubric evals (Anthropic), nothing (CrewAI/spec-kit/Kiro) | PMOS's harness is the strongest of its kind; trajectory-level eval and end-task quality remain open |

### 14.3 What nobody does that PMOS already does

- **Benchmark-computed, cost-tiered per-role model selection with fallback ladders** (`recommend.py`). Not one of the surveyed systems selects models from benchmark data at launch; the state of the art elsewhere is hand-picked per-role fields (MetaGPT config, Claude subagent `model:`) or sticky models (Roo Code).
- **Stable artifact IDs + deterministic linter + RDF/SPARQL traceability.** spec-kit/Kiro have file conventions but no enforced ID graph; BMAD has forward/back traceability but as a checklist, not a queryable store.
- **A spend ledger that separates measured vs estimated, records failed runs, calibrates from project history, and gates waves by exit code.** MetaGPT's `NoMoneyException` is the only comparable mechanism and it's a blunt global axe.
- **A deterministic, free, mutation-tested protocol harness.** AutoGenBench (repeat + isolation) is the closest competitor, but it evaluates *tasks*, not *gate decisions*.

---

## 15. Lessons for PMOS

Mapped to PMOS components (knowledge base, roster/model selection, gates, traceability, cost ledger, eval harness), each with the evidence and an effort estimate. **S** = hours; **M** = days; **L** = weeks.

### L-1. Stop re-reading ORCHESTRATOR.md: adopt the OpenHands condenser pattern at the protocol level (KB / protocol docs) — **M**
The 300-line protocol is re-read in full every session. OpenHands' `LLMSummarizingCondenser` keeps the head and tail of a long event log and summarizes the middle (docs: keep first N + last M, summarize between, target ~half, record `forgotten_event_ids`). For PMOS this maps to: `state.py` already knows the current stage — emit **only the stage-relevant protocol excerpt** (head = global rules, tail = next-step rules) into each worker prompt, and keep the full manual for humans. Even simpler: split ORCHESTRATOR.md into a stable core (`RULES.md`, ~80 lines) + per-stage files that `state.py` resolves. Evidence: OpenHands condenser docs; Claude Code's Explore/Plan skipping CLAUDE.md for speed; Anthropic's "spawn fresh subagents with clean contexts." Effort **M** (touches spawn template + state.py + docs).

### L-2. Add recency/importance weighting to KB recall ranking (knowledge base) — **S/M**
PMOS's RRF fuses BM25 + vectors with no time dimension; CrewAI's unified memory ranks by `semantic 0.5 + recency 0.3 + importance 0.2` with `recency_half_life_days` decay, and scopes recall to a subtree. Concretely: multiply RRF scores by a per-chunk recency factor derived from the chunk's source-file mtime (ADR-012 superseding ADR-005 should rank higher; the KB already prunes superseded content at re-index, but decay smooths the transition). Also consider per-role **importance priors** (the shared rules namespace already outranks scraped top-ups — make that a tunable weight like CrewAI's). Evidence: https://docs.crewai.com/en/concepts/memory (weights table). Effort **S** for mtime decay, **M** if you add LLM-inferred importance (don't — see skepticism in §4: LLM analysis per save is costly and non-deterministic; PMOS's deterministic priorities are the better default).

### L-3. EARS-format acceptance criteria + a pre-GATE-2 requirements analysis pass (gates, traceability) — **S**
Kiro's requirements use EARS (`WHEN <trigger> THE SYSTEM SHALL <response>`) explicitly "to provide structured, testable requirements," and Kiro offers an **Analyze Requirements** step that flags "logical inconsistencies, ambiguities, conflicting constraints, and gaps" before design. PMOS already has R-NNN/A-NNN; adopt (a) an EARS template for A-NNN in `templates/plan.md`, and (b) a GATE-2 checklist (in `ORCHESTRATOR.md` step 8) asking the PM to re-read requirements for contradictions — or better, a cheap "adversarial requirements review" task for the QA or legal role. Evidence: https://kiro.dev/docs/specs/feature-specs/ and https://kiro.dev/docs/specs/ (Analyze Requirements). Effort **S**.

### L-4. Widen the failure taxonomy: retry vs replan vs decompose, plus stall detection (roster/execution) — **M**
PMOS's ladder handles "the model failed." CAMEL's Workforce adds a **failure-analysis → `RecoveryDecision`** pipeline where recovery is one of *retry (with feedback), replan, decompose differently*; Magentic-One re-plans wholesale when progress stalls for a few cycles (its Progress Ledger asks: *is the team making progress? is it looping?*). Concretely: give the coordinator a decision rule — (1) model/transient error → existing ladder; (2) task failed QA with the same root cause twice → *replan* (have the PM re-split the task) or *decompose* (split into smaller tasks) before the 4-ladder cap is reached; (3) a stall counter on wave-4→wave-3 rework loops (e.g. 2 loops → user-facing checkpoint with a re-plan proposal). Evidence: https://docs.camel-ai.org/key_modules/workforce/ (RecoveryDecision, task lifecycle diagram), https://arxiv.org/abs/2411.04468 (ledgers, re-plan on stall). Effort **M** (protocol change + log fields + a new `state.py` check).

### L-5. Per-worker timeout + per-task budget flags in the cost ledger (cost ledger) — **S/M**
CAMEL's `task_timeout_seconds` and `graceful_shutdown_timeout` bound runaway tasks; OpenHands ships `max_budget_per_task` (default 0.0 = off) and `max_iterations` (100). PMOS gates at the *wave* level; add (a) an optional `timeout_min` per task in the wave spawn (host permitting), and (b) a `--cap` parameter to `cost.py estimate` so a single task's ladder can be budget-limited (the ladder already logs failed runs, so the cap is computable from the ledger). Evidence: https://docs.camel-ai.org/key_modules/workforce/; https://docs.openhands.dev/openhands/usage/v0/advanced/V0_configuration-options. Effort **S** for timeout docs/config, **M** for per-task cap in `cost.py`.

### L-6. Effort-scaling heuristics for wave spawns (roster/model selection, cost) — **S**
Anthropic's orchestrator prompt encodes spawn-count rules (1 subagent for simple fact-finding, 2–4 for comparisons, 10+ for complex research) because raw autonomy over-spawns ("expect 2–3 months of iteration before your version stops spawning 50 subagents for a one-line question"). PMOS's roster is human-approved at GATE 1, which already prevents this; the cheap add is a **roster justification rule**: the PM's `roster-proposal.md` must state, per role, the *task count it will own*, and GATE 1 shows an estimated total-spawn count. Evidence: https://www.anthropic.com/engineering/multi-agent-research-system (delegation rules; 15× token cost). Effort **S** (template + prompt wording).

### L-7. spec-kit-style "converge" pass to close the semantic-gap hole in the eval harness (eval harness) — **M**
PMOS's harness "proves the machinery and the gate decisions, not the quality of what agents write" (EVALUATION.md), and its fixtures are deterministic — a deliberate, honest boundary. spec-kit's `/speckit.converge` closes exactly that gap: it assesses the *codebase against spec/plan/tasks* and appends remaining work as new tasks, looping until "Converged." Add an **optional, clearly-labeled level-5.5 step**: after QA passes, a cheap-model worker runs a converge-style audit (spec → plan → tasks → code, using `trace.py coverage` + `kg.py` queries as the structural skeleton and a rubric prompt for semantics), producing a `convergence.md` with findings appended as new T-NNNs. Evidence: https://github.com/github/spec-kit (converge command; "Repeat steps 4 and 5 until converge reports Converged"). Effort **M**.

### L-8. Export T-NNN tasks to GitHub issues (traceability) — **S/M**
spec-kit's `/speckit.taskstoissues` converts the task list into GitHub issues for tracking and execution, giving external, queryable traceability. PMOS's `artifacts.py` already lints tasks; add a `tools/export_issues.py` that emits a T-NNN → issue mapping (id in the issue body/title, `satisfies` in the description) with an idempotent re-run (match on the T-NNN marker). Optional — most valuable in brownfield mode where human developers will pick up tasks. Evidence: https://github.com/github/spec-kit (taskstoissues row). Effort **S/M**.

### L-9. Structured wave-events trace for post-hoc evaluation (eval harness / observability) — **M**
AgentScope's thesis — "agents you can see, understand, trust" — and the eval-literature consensus (evaluate final output, trajectory, and single steps) both point at PMOS's biggest observability gap: `log.md` is prose, `costs.jsonl` is spend-only. Add a `.pmos/waves.jsonl` (append-only, one JSON object per wave/worker: role, task ids, model tried, ladder index, outcome, gate result, KB queries count, defects) so the "per-run project metrics" (README level 4) become machine-comparable across projects. This is the trajectory-level eval that AutoGenBench and SWE-agent's `.traj` files provide in their domains. Evidence: https://github.com/agentscope-ai/agentscope; https://github.com/SWE-agent/SWE-agent (per-step `.traj`); https://cameronrwolfe.substack.com/p/agent-evals. Effort **M**.

### L-10. Kill the host lock-in: ship adapters, keep the protocol host-agnostic (roster / portability) — **L (staged: S first)**
PMOS's weakest spot per the brief is being "locked to one agent host's spawn/list-models/usage primitives." The field's counter-example is spec-kit: **one process, 30+ agent integrations**, delivered by generating host-specific command files (`.claude/commands/`, Copilot, Codex, Cursor). BMAD ships the same method as skills for multiple tools. Staged plan: **(S)** document the host contract precisely (the ~4 primitives PMOS needs — spawn-with-model, list_models, usage, session resume) in a `HOST-ADAPTER.md`, and generate a Claude Code subagent set (`.claude/agents/*.md` + commands) from `roster.json` so the template at least *runs* on a second host; **(M)** abstract the three primitives behind `tools/host.py` with a jcode backend and a mock backend (the mock backend doubles as the eval harness's host — no model spawning today, but a contract-tested one tomorrow); **(L)** a second real backend (e.g. Claude Code headless or OpenHands SDK), validated by running `eval_project.py` fixtures through it. Evidence: https://github.com/github/spec-kit (integrations list); https://github.com/bmad-code-org/bmad-method (multi-tool skills); https://code.claude.com/docs/en/sub-agents (portable subagent YAML). Effort **S→M→L** as staged.

### L-11. Consider a cross-project experience namespace in the KB (knowledge base) — **M**
ChatDev's Experiential Co-Learning (experience pool across tasks) and MetaGPT's `exp_pool` (BM25/chroma + LLM reranker) are the field's attempts at "what we learned last project." PMOS's KB is per-project by design (portable, gitignored DB), but a **read-only optional `~/.pmos-experience/` namespace** (per-role markdown facts, indexed at bootstrap with a lower priority tier than project facts) would let retry/wave outcomes from past projects inform new ones without polluting the project. Keep it optional and bounded — the existing 150K cap logic extends naturally (overflow drops the lowest-priority chunks first; experience would be the lowest tier). Evidence: https://arxiv.org/abs/2312.17025; https://raw.githubusercontent.com/geekan/MetaGPT/main/config/config2.example.yaml (`exp_pool`). Effort **M**.

### L-12. Pre-flight deterministic validation of worker output, SWE-agent style (gates) — **S**
SWE-agent validates every agent output before it reaches the environment: parse errors re-prompt (max 3), action blocklists, `bash -n` syntax pre-checks, timeout counters. PMOS already mandates "run `artifacts.py` before reporting done," but nothing *enforces* it at the host level. Where the host supports tool hooks (Claude Code's PreToolUse hooks; OpenHands security analyzers with `security_risk` classification and action confirmation), add an adapter hook that runs `artifacts.py --strict` and blocks "done" reports on lint errors — turning a prompt rule into a host-enforced gate. Evidence: https://code.claude.com/docs/en/sub-agents (hook example that blocks writes and feeds the message back); https://docs.openhands.dev/sdk/guides/security; https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/agents.py. Effort **S** (per-host hook file, guarded by L-10's adapter layer).

### L-13. Keep the model ladder, but add the provider-chain lesson from the eval side (roster/model selection) — **S**
Nothing in the survey matches PMOS's benchmark-computed ladders — that's the moat. Two cheap sharpenings from the survey: (a) Anthropic's finding that **token spend is the strongest predictor of output quality** argues for recording per-role *quality* (acceptance pass rate by model) into the ledger so future `recommend.py` runs can downweight models that historically fail QA — PMOS already records `--status ok|failed` per run; aggregate by model in `cost.py report`. (b) Roo Code's **sticky model per mode** suggests honoring a "user's last approved choice per role" cache (`~/.jcode/pmos-team-defaults.json` already does this). Evidence: https://www.anthropic.com/engineering/multi-agent-research-system; https://docs.roocode.com/features/custom-modes. Effort **S**.

### L-14. GATE-2 should show the same trace tree spec-kit/Kiro show, plus BMAD's PASS/CONCERNS/FAIL (gates) — **S**
`trace.py coverage` already renders scope→task→criterion; the survey's gate presentations (Kiro phase approvals, BMAD readiness gates, spec-kit analyze) suggest the user-facing GATE-2 summary should be a *verdict*: `PASS / CONCERNS / FAIL` with the top concerns as a bulleted list (existing `artifacts.py` warnings), not just a dump. Purely presentational; no machinery change. Evidence: https://github.com/bmad-code-org/bmad-method (readiness gate "PASS/CONCERNS/FAIL, stop on FAIL with findings"); https://kiro.dev/docs/specs/ (phase approvals). Effort **S**.

### L-15. Prefer PMOS's deterministic design in the two places the survey tempts you to get fancy — **(decision, not effort)**
- **Do not** replace the linter/RDF checks with LLM-based "analyze" steps as the *gate* — spec-kit's analyze is prompt-driven and can be fooled; keep LLM analysis as the level-5.5 *add-on* (L-7). Deterministic structure + LLM semantics is the BMAD-validated split.
- **Do not** adopt CrewAI's LLM-analyzed memory saves wholesale — per-save LLM calls add cost and nondeterminism; PMOS's priority field + re-index pruning achieves the same hygiene deterministically. Steal only the recency weighting (L-2).
- **Do not** copy MetaGPT/ChatDev's fixed SOP pipelines — PMOS's roster right-sizing (impact-surface justification) and wave gates are the managed version of the same idea, without the "rewrite code to change the flow" tax. (MetaGPT issue #1031 also shows the cost-manager wiring was never fully reliable; PMOS's exit-code-gated ledger is the hardened version.)

---

## 16. One-paragraph verdict

PMOS is not a follower in this field — it is the only system surveyed that combines benchmark-computed per-role model selection, a measured spend ledger with budget gates, stable artifact IDs with deterministic linting and RDF traceability, and a deterministic mutation-tested protocol harness. The survey's highest-value adoptions are: (1) OpenHands-style context condensation applied to PMOS's own protocol docs (L-1), (2) CAMEL/Magentic-One-style failure taxonomy with replan/decompose and stall detection (L-4), (3) a spec-kit-style semantic converge pass layered on top of the deterministic harness (L-7), (4) Kiro's EARS requirements + pre-design analysis (L-3), and (5) a staged host-adapter layer to break jcode lock-in, following spec-kit's 30-integration playbook (L-10). Meanwhile, the 2024→2026 trend of simplification (SWE-agent → mini-swe-agent, BMAD v6, spec-kit 1.0) is a reminder to re-validate every protocol rule against current models — the same reason PMOS's own CI checks, fixture corpus, and `validate.py` are the right investments.

---

## 17. Source index (all URLs cited above)

- MetaGPT: https://github.com/FoundationAgents/MetaGPT · https://arxiv.org/abs/2308.00352 · https://docs.deepwisdom.ai/main/en/guide/tutorials/multi_agent_101.html · https://raw.githubusercontent.com/geekan/MetaGPT/main/config/config2.example.yaml · https://github.com/geekan/MetaGPT/blob/main/metagpt/team.py · https://github.com/geekan/MetaGPT/issues/562 · https://github.com/geekan/MetaGPT/issues/1031
- ChatDev: https://github.com/OpenBMB/ChatDev · https://arxiv.org/abs/2307.07924 · https://arxiv.org/abs/2312.17025 · https://arxiv.org/abs/2406.07155
- AutoGen/AG2/MAF: https://github.com/ag2ai/ag2 · https://docs.ag2.ai · https://github.com/microsoft/agent-framework
- Magentic-One: https://arxiv.org/abs/2411.04468 (and v1 HTML)
- CrewAI: https://github.com/crewAIInc/crewAI · https://docs.crewai.com/en/concepts/memory · https://docs.crewai.com/en/concepts/tasks
- AgentScope: https://github.com/agentscope-ai/agentscope · https://arxiv.org/abs/2402.14034 · https://arxiv.org/abs/2508.16279
- CAMEL: https://github.com/camel-ai/camel · https://docs.camel-ai.org/key_modules/workforce/
- OpenHands: https://github.com/OpenHands/OpenHands · https://github.com/OpenHands/software-agent-sdk · https://docs.openhands.dev/sdk/arch/condenser · https://docs.openhands.dev/openhands/usage/v0/advanced/V0_configuration-options · https://docs.openhands.dev/sdk/guides/security
- SWE-agent: https://github.com/SWE-agent/SWE-agent · https://arxiv.org/abs/2405.15793 · https://swe-agent.com/latest/usage/ · https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/agents.py
- Claude Code: https://code.claude.com/docs/en/sub-agents · https://code.claude.com/docs/en/agent-teams · https://www.anthropic.com/engineering/multi-agent-research-system
- spec-kit: https://github.com/github/spec-kit · https://github.blog/news-insights/company-news/welcome-home-agents/
- Kiro: https://kiro.dev/docs/specs/ · https://kiro.dev/docs/specs/feature-specs/ · https://kiro.dev/docs/specs/feature-specs/requirements-first/ · https://kiro.dev/docs/steering/ · https://kiro.dev/blog/introducing-kiro/
- BMAD-METHOD: https://github.com/bmad-code-org/bmad-method
- Extras: https://docs.roocode.com/features/custom-modes · https://github.com/OpenBMB/AgentVerse · https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation · https://mlflow.org/articles/ai-agent-evaluations-a-developers-practical-guide/ · https://cameronrwolfe.substack.com/p/agent-evals
