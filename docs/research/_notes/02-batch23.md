# Batch 2/3 notes (verified 2026-08-24)

## OpenHands
- Repo: https://github.com/OpenHands/OpenHands (84.9k stars; Agent Canvas frontend + Agent Server + automation repo boundaries)
- SDK: https://github.com/OpenHands/software-agent-sdk — Python/REST APIs; LLM/Agent/Conversation/Tool; TaskTrackerTool; SWE-bench badge 77.6; tech report arXiv:2511.03690
- Condenser: https://docs.openhands.dev/sdk/arch/condenser — NoOp/LLMSummarizing/Pipeline condensers; max_size default 120 events; keep first N + last M, summarize middle; target view max_size//2; Condensation event with forgotten_event_ids; append-only event log
- Budget: https://docs.openhands.dev/openhands/usage/v0/advanced/V0_configuration-options — max_budget_per_task default 0.0 (no limit); max_iterations default 100
- Cost tracking: conversation.conversation_stats.get_combined_metrics().accumulated_cost (security guide example)
- Security: https://docs.openhands.dev/sdk/guides/security — security_risk param on actions, LLMSecurityAnalyzer, configurable security policy template, action confirmation

## SWE-agent
- Repo https://github.com/SWE-agent/SWE-agent (NeurIPS 2024; maintenance-only mode, superseded by mini-swe-agent https://mini-swe-agent.com)
- Paper arXiv:2405.15793 (ACI design; search tools can exhaust cost budget/context window)
- Loop detail (sweagent/agent/agents.py; mirrored by deep-dive guide): max_requeries=3 on FormatError -> format_error_template re-injection; action blocklist; bash -n syntax precheck; consecutive timeout counter; trajectory saved after every step; LiteLLM tracks cost; config YAML: agent/env/problem_statement sections; history_processors for context management

## Claude Code
- Subagents docs https://code.claude.com/docs/en/sub-agents: own context window, custom system prompt, tool allowlists, model field (opus/sonnet/haiku/inherit), hooks for tool validation (PreToolUse exit 2 blocks); built-in Explore (read-only, model capped at Opus, skips CLAUDE.md for speed), Plan; description-based delegation; plugins for distribution; "control costs by routing tasks to faster, cheaper models like Haiku"
- Agent teams https://code.claude.com/docs/en/agent-teams: experimental (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1), lead session + teammates, shared task list + direct messaging, higher token cost, known limitations (resumption, coordination, shutdown)
- Anthropic multi-agent research system https://www.anthropic.com/engineering/multi-agent-research-system: Opus lead + Sonnet subagents +90.2% internal research eval; ~15x tokens; effort scaling heuristics (1 agent simple / 2-4 comparison / 10+ complex); artifacts to filesystem + lightweight refs; evals: end-state rubrics + ablations; sync waves stall on slowest subagent

## spec-kit
- https://github.com/github/spec-kit (131k stars; 1.0.1 Aug 2026; MIT)
- Commands: constitution, specify, clarify, plan, tasks, taskstoissues, implement, converge, analyze (cross-artifact consistency/coverage), checklist ("unit tests for English"); bug extension assess/fix/test; assess extension go/needs-clarification/kill
- Extensions/presets/bundles; 30+ agent integrations; specs/<feature>/ artifacts; "specifications become executable"

## Kiro (AWS; closed-source product, public docs)
- https://kiro.dev/docs/specs/: .kiro/specs/<name>/{requirements.md,design.md,tasks.md}; three-phase workflow with approval between phases; task execution UI with status; Quick Spec = one pass without approval gates; Correctness (property-based testing, IDE only)
- https://kiro.dev/docs/specs/feature-specs/: EARS notation; Analyze Requirements (inconsistencies/ambiguities/gaps before design); Refine regenerates design+tasks when requirements change
- https://kiro.dev/docs/steering/: .kiro/steering/*.md persistent project knowledge; inclusion modes always/fileMatch/manual; global ~/.kiro/steering; AGENTS.md support

## BMAD-METHOD
- https://github.com/bmad-code-org/bmad-method (52.2k stars; v6.11.0; MIT; npm bmad-method)
- README: AiDD; delivery loop Clarify/Plan/Build/Learn; right-sized process; durable context; modules: bmm core, bmad-builder, creative suite, test architect (tea), bmad-loop (unattended epic build/verify/retro), game dev studio
- v6 = SKILL.md-based agents + workflows; TOML 3-layer customization (skill defaults -> team -> user); deterministic script cores (sprint_plan.py, 11 tests) with LLM judgment on top; readiness gate PASS/CONCERNS/FAIL + forward/back traceability inside sprint-planning; build review lenses: Blind Hunter, Edge Case Hunter, Acceptance Criteria Audit, Verification Gap (Fits AC? gate between Implement and Review); deterministic skill validator tools/validate-skills.js (13 rules, CI, <1s); party-mode append-only memlog memory standard

## CAMEL Workforce
- https://docs.camel-ai.org/key_modules/workforce/: Workforce(description, children, coordinator_agent, task_agent, new_worker_agent, graceful_shutdown_timeout=15, task_timeout_seconds, share_memory, use_structured_output_handler, callbacks); SingleAgentWorker (AgentPool reuse), RolePlayingWorker; task lifecycle: decompose -> assign -> execute -> retry/replan/decompose on failure; RecoveryDecision pydantic model (failure analysis dictates recovery strategy); WorkerConf/TaskResult/TaskAssignment; HumanToolkit HITL via tools; per-worker model via ModelFactory example
- CAMEL repo https://github.com/camel-ai/camel: OWL workforce optimized for GAIA (top open-source claim)

## AgentScope
- arXiv:2402.14034: message exchange core; built-in + customizable fault tolerance; utility monitor; automatic prompt tuning; actor-based distribution; zero-code workstation
- arXiv:2508.16279 (1.0 developer-centric); repo 29.4k stars, v2.0.7 (Aug 2026); Studio observability; channels (DingTalk etc.)

## AgentVerse (extra)
- https://github.com/OpenBMB/AgentVerse: task-solving + simulation; ICLR 2024 (arXiv:2308.10848); expert recruitment -> collaborative decision making -> action -> evaluation loop; software dev demos

## Roo Code (extra)
- https://docs.roocode.com/features/custom-modes: custom modes YAML (slug/name/roleDefinition/groups tool permissions/whenToUse/customInstructions), global or project, import/export single YAML, marketplace; sticky model remembered per mode; Orchestrator (boomerang) mode decomposes via new_task tool using whenToUse

## Microsoft Agent Framework (context for AutoGen lineage)
- https://github.com/microsoft/agent-framework: successor to AutoGen/Semantic Kernel; Python/.NET/Go; graph workflows (sequential/concurrent/handoff/group) with checkpointing, streaming, HITL, time-travel; middleware; declarative YAML agents; agent skills; OpenTelemetry observability; DevUI; AF Labs benchmarking/RL

## Magentic-One numbers (arXiv:2411.04468v1)
- GAIA 38%, WebArena 32.8%, AssistantBench 27.7; Orchestrator Task Ledger + Progress Ledger; re-plans on stall; AutoGenBench harness with repetition + isolation controls
