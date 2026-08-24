# Notes batch 1: MetaGPT, ChatDev, AutoGen/AG2, CrewAI, AgentScope

## MetaGPT (FoundationAgents/MetaGPT, 70k stars; paper arXiv:2308.00352, ICLR 2024)
Sources: https://github.com/FoundationAgents/MetaGPT, https://arxiv.org/abs/2308.00352, https://docs.deepwisdom.ai/main/en/guide/tutorials/multi_agent_101.html
- What: "First AI Software Company" — SOP-encoded assembly line: ProductManager -> Architect -> ProjectManager -> Engineer -> QA. One CLI command: `metagpt "write a cli flappy bird game"`.
- Roles: Python classes (Role subclasses with Actions). Assignment = fixed SOP pipeline; Role `_watch`es upstream Action message types (subscription). `_observe/_think/_act/publish_message` loop over shared Environment message pool.
- Context sharing: publish-subscribe message pool (Environment); each role watches only message types from chosen upstream actions => structural context bounding (paper: "communicative dehallucination"/structured communication to reduce cascading hallucinations). Per-role Memory (short-term; retrieval in _observe/_think/_act). Also has RAG example (arXiv 2406.14637, "MetaGPT with RAG").
- Model assignment: per-role LLM config in config2.yaml (global llm config + roles can override; e.g. examples use different models). Actually config.yaml has llm section; Role can set own llm. (verify)
- Cost: tracks token/cost (llm cost tracking in logs; has "max_budget"? — paper mentions cost control: software company budget. Need verify: MetaGPT has usage cost tracking in Team/Environment? There is `metagpt/utils/cost_manager.py` CostManager with max_budget). YES: cost_manager.py exists with max_budget (default e.g. 5 USD?) — verify on github.
- Artifacts: structured documents (PRD, design doc, task list, code files) as intermediate artifacts passed between roles; paper claims SOP + structured docs reduce cascading hallucination vs free chat.
- QA/verification: QA engineer role writes+runs tests; paper uses executability + HumanEval/MBPP pass rate on SoftwareDev benchmark (their own; 7 small projects).
- Failure: limited; retries on LLM call (llm retry). Not much escalation.
- Evaluation: SoftwareDev benchmark (paper): executability and pass rate on 7 projects; comparison vs ChatDev. SWE-bench runner exists in repo (tests run_swe_agent_for_benchmark.py) — MetaGPT also evaluated on SWE-bench.
- Weaknesses: largely fixed 5-role pipeline; research slowed (last substantive README update Oct 2025; core code mostly 2023-2024); cost guardrail is crude.

## ChatDev (OpenBMB/ChatDev, 34.1k stars; arXiv:2307.07924 ACL 2024)
Sources: https://github.com/OpenBMB/ChatDev, https://arxiv.org/abs/2307.07924
- What: chat-chain waterfall: CEO, CPO, CTO, programmer, reviewer, tester, art designer; phases (design/coding/testing/documenting) each = dual-agent sub-chat (instructor + assistant) with "communicative dehallucination". ChatDev 2.0 (Jan 2026): rebuilt as node/graph workflow engine ("Dev All"), MCP support, Mem0 memory integration, multi-provider models.
- Roles: defined in CompanyConfig/*.json / phase configs (ChatChainConfig.json, PhaseConfig.json) — role names + system prompts per phase. Assignment = fixed phase chain; user composes custom chains.
- Context: chat chain; each phase's dialogue summarized; "communicative dehallucination": assistant asks instructor for more info before answering. Memory: ChatDev 2.0 integrates Mem0 (per user/agent scope). 1.0: no long-term memory; Experiential Co-Learning (arXiv:2312.17025) adds experience pool across runs; MacNet (arXiv:2406.07155) scales to 1000+ agents on graphs.
- Model: 2.0 multi-provider (OpenAI, DeepSeek etc.), model configurable per... (config). 1.0: single model configured globally (config2.json). No per-role model selection strategy documented.
- Cost: paper reports ~$0.30-1.00 per software; no runtime budget guardrail. (weak)
- Artifacts: code files, docs in WareHouse/<task> directory; no stable ids linking requirements->code.
- QA: reviewer+tester phases; self-reflection on test execution; human can inject at phases (ChatChain has "self-improvement"?). Human involvement: no mandatory gates by default (optional manual).
- Failure: retries within dialogue; no model fallback ladder.
- Evaluation: paper uses 70 software tasks across 3 modality categories, manual assessment of executability/completeness/efficiency (LLM cost/time). MacNet has MATH/FiveDice etc. No standing harness in repo beyond examples.
- Weakness: eval is small and manual; waterfall is fixed; 1.0 largely unmaintained, 2.0 is a rewrite.

## AutoGen -> AG2 (ag2ai/ag2, "AgentOS"; microsoft/autogen now Microsoft Agent Framework)
Sources: https://github.com/ag2ai/ag2, https://docs.ag2.ai
- What: AG2 (AutoGen fork) — agent chat framework: AssistantAgent, UserProxyAgent, GroupChat, nested chats, teams, handoffs; "open-source AgentOS". NOTE: Microsoft's AutoGen moved to Microsoft Agent Framework (microsoft/agent-framework) in late 2025; the community fork AG2 continues.
- Roles: agents defined in code (AssistantAgent with system_message, tools); GroupChatManager selects speaker (round_robin / LLM auto / custom selector_func). Handoffs (Swarm pattern) — agent transfers control by returning handoff message.
- Context: conversation history passed in group chat; GroupChatManager can summarize (max_round, admin_name); TransformMessages middleware for context limits (message token limit, summary). Knowledge: RAG via retrievers (KnowledgeStore/VectorDB retriever in contrib); Memory interface (add/retrieve/update context). Telemetry (OpenTelemetry). Evaluation docs: ag2 has "Evaluation" section (agent-based eval, e.g. with AG2 benchmark?) — docs.ag2.ai/docs/user-guide/evaluation/.
- Model: config_list (OAI_CONFIG_LIST) — list of LLM configs; per-agent llm_config picks model; filter_dict for model selection; supports fallback by trying next config? config_list with filters lets different agents use different models. No automatic benchmark-based selection.
- Cost: LLM config "config_list" + cost tracking? AutoGen had token usage summary (print_usage); AG2 has usage tracking via middleware? (verify: AG2 docs telemetry/usage). Magentic-One (Microsoft) had ledger + progress ledger + stall detection.
- Artifacts: code executor writes files; no requirement-level ids.
- QA/verification: code execution + termination conditions (TextMentionTermination, MaxMessage); UserProxyAgent = human-in-the-loop (human_input_mode ALWAYS/TERMINATE/NEVER) — human gate via human_input_mode.
- Failure: retry via max_consecutive_auto_reply, human takeover; nested chats as error recovery (carryover); no automatic model fallback ladder (config_list order is a kind of fallback list).
- Evaluation: AG2 docs "Evaluation" — uses GAIA? Actually AutoGen team published Magentic-One on GAIA, WebArena, SWE-bench? Magentic-One (Microsoft, Nov 2024): Orchestrator with Task Ledger + Progress Ledger, stall detection (re-plan after N stalls), agents WebSurfer, FileSurfer, Coder, Terminal. Evaluated GAIA (38% GPT-4o), AssistantBench, SWE-bench? GAIA 38% vs 33% human? Actually Magentic-One scored 38% overall GAIA vs HLT (human baseline?). Note numbers carefully.
- Weakness: framework, not an SDLC template; no built-in project management.

## CrewAI (crewAIInc/crewAI, 57.5k stars)
Sources: https://github.com/crewAIInc/crewAI, https://docs.crewai.com/en/concepts/memory
- What: role-playing agent framework: Crews (role agents + tasks) and Flows (event-driven deterministic orchestration). Agents defined by role/goal/backstory + tools + llm. Tasks with expected_output, context dependencies, output_file, async_execution, guardrail (validation function/agent), human_input flag.
- Roles: declarative (YAML in crewai create scaffolds: agents.yaml, tasks.yaml). Process sequential or hierarchical (manager LLM delegates). Flows give deterministic state machine + @start/@listen/@router decorators, structured state (Pydantic), persistence (SQLite via @persist).
- Context/memory: unified Memory (2025-2026 rewrite): single Memory class, hierarchical scopes (/project/alpha, /agent/researcher), LLM-analyzed save (scope/category/importance inference), composite recall score = semantic+recency+importance (weights configurable, recency_half_life_days), consolidation (dedup >0.85 sim), adaptive-depth recall (exploration_budget LLM rounds), LanceDB storage, OpenAI text-embedding-3-large default. Crew memory=True auto-extracts facts after each task, injects recall before each task. Agent can get scoped private view memory.scope(...).
- Model: per-agent llm param (any LiteLLM model string); no automatic selection; Crew default llm.
- Cost: not a first-class budget; (crewai telemetry tracks usage; no budget guardrail in OSS core — verify. There's max_iter, max_rpm (rate limit!), max_execution_time per task; respect_rate_limit / rate_limit handling. Cost: I don't think OSS CrewAI has cost cap; CrewAI AMP platform maybe.)
- Artifacts: Task.output_file writes files; no stable id scheme; context=[task] passes outputs.
- QA/gates: Task guardrail (validate output, retry up to max_retries with feedback), human_input=True on a task = human gate before finishing task.
- Failure: max_iter on agent (default 20) with "must give final answer" reset; guardrail retry; no model fallback ladder.
- Evaluation: CrewAI has "crewai test"? No. Testing via evals? CrewAI AMP/enterprise has evals; OSS: none standard. (be skeptical)
- Weakness: no SDLC artifact traceability; memory is general-purpose; eval absent in OSS.

## AgentScope (agentscope-ai/agentscope, 29.4k stars; arXiv:2402.14034 + 1.0 paper 2508.16279)
Sources: https://github.com/agentscope-ai/agentscope, https://arxiv.org/abs/2402.14034
- What: Alibaba's developer-centric multi-agent platform; "agents you can see, understand, trust" — emphasis on observability: AgentScope Studio (web UI, tracing), distributed actor-based runtime, fault tolerance. 2.0 (2026): ReActAgent, async, MCP, session/history management, memory, planing?; AgentScope Workstation? (zero-code workstation). Agent service with channels (DingTalk etc.).
- Roles: agents as code (ReActAgent with sys_prompt + toolkit); pipelines (sequential/conditional/loop), MsgHub for broadcast; no prescribed SDLC roles but has examples (werewolf, software dev?).
- Context: Msg-based; message hub; memory (in-agent history); session persistence; context via structured Msg. Token budget: does AgentScope have "context management"? 1.0 paper: automatic parallel optimization; fault tolerance: rule-based + custom (retry with parse_func, max_retries for LLM call, service wrappers with retry).
- Model: model config JSON (config_name -> model per agent); different agents can use different configs. Auto prompt tuning mechanism (paper).
- Cost: utility monitor tracks usage (AgentScope Studio shows token usage/cost?); paper mentions "utility monitor". No budget cap guardrail documented.
- Artifacts/QA: none SDLC-specific. Fault-tolerance focus: retry parsers, custom handlers, rule-based correction.
- Evaluation: 1.0 paper describes eval? AgentScope has "agentscope.eval"? Not prominent. It hosts AgentBench? No — AgentBench is THU. AgentScope has an evaluation module? (need care: don't assert).
- Weakness for PMOS comparison: infra framework, not SDLC orchestration; but strong on observability/tracing + fault tolerance patterns + actor distribution.

## GitHub Agent HQ (context, Oct 2025 Universe)
Sources: https://github.blog/news-insights/company-news/welcome-home-agents/, https://visualstudiomagazine.com/articles/2025-10-28/github-introduces-agent-hq...
- Mission control: assign/steer/track multiple coding agents (Copilot + Claude, Codex, Jules, Devin?, xAI) across surfaces; plan mode; AGENTS.md as source-controlled agent config; branch controls for agent code; code review step inside Copilot coding agent before human review; enterprise control plane (audit, policy). Agent work item = issue assigned to agent; async PR-based handoff.

## Anthropic multi-agent research system (Claude Code lineage)
Source: https://www.anthropic.com/engineering/multi-agent-research-system
- Orchestrator-worker; lead (Opus 4) spawns 3-5 Sonnet 4 subagents with self-contained task briefs (objective, output format, tools, boundaries); parallel own contexts; condensed returns via shared filesystem/artifacts + lightweight refs; citation agent separately. +90.2% vs single Opus on internal research eval; token spend strongest predictor of quality; effort scaling rules (1 agent simple, 2-4 comparisons, 10+ complex). Slow subagent stalls wave (sync waves); failures: spawn fresh subagents when context limits approach; eval = end-state rubric evals on ~20 internal research tasks + ablations; ~$15/query cost mentioned (verify: "up to $15" was in blog? actually blog says multi-agent uses ~15x tokens; cost per query $15 for complex — I recall the blog mentioned $15 for a complex query). Keep: "blog notes multi-agent ~15x token usage of chat".
