# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
uv run pytest -q

# Run a single test file
uv run pytest tests/test_trace_renderer.py -q

# Run a single test by name
uv run pytest -q -k "test_trace_renderer_handles_full_trace"

# Launch the Gradio UI (requires ANTHROPIC_API_KEY in .env or env)
uv run revere-ui

# Run a single pipeline turn from the CLI
uv run revere-run

# Install deps
uv sync
```

## Architecture

This is a Civic LLM candidacy project: an agentic political-events chatbot with structured reasoning and an auditable trace.

### Request flow

Every user message passes through a deterministic 7-stage sequential pipeline (`Orchestrator.run_turn`):

```
S1 intake → S2 scope → [short-circuit if OOS] → S3 plan → [search I/O] → S4 evidence → S5 perspectives → S6 verify → S7 compose
```

- **S1** (`run_s1_intake`): Normalizes the query into `IntakeAnalysis` (canonical form, modality, etc.)
- **S2** (`run_s2_scope`): LLM-based scope gate returning `ScopeDecision`. If `in_scope=False`, pipeline stops and `ScopeDecision.suggested_redirect` is the response. This is the anti-keyword-matching stage.
- **S3** (`run_s3_plan_search`): Decides whether Tavily retrieval is needed, returns `SearchPlan` with 0–3 queries.
- **Search execution**: Pure I/O (no LLM). Runs Tavily queries, deduplicates hits, caps at `max_unique_hits`.
- **S4** (`run_s4_source_quality`): Scores each hit and produces `EvidenceBase`. If no search ran, documents the model-knowledge limitation.
- **S5** (`run_s5_perspectives`): Multi-perspective synthesis with steelmanning, returns `PerspectiveAnalysis`.
- **S6** (`run_s6_verification`): Chain-of-Verification pass, returns `VerificationReport` with per-claim confidence.
- **S7** (`run_s7_compose_check`): Final composition + 6-principle neutrality self-check, returns `FinalResponse`.

Each stage is a separate file in `revere_agent/agent/stages/` and calls `run_llm_stage()` from `_common.py`, which loads the charter + stage prompt and calls `LLMProvider.call_structured()` for a Pydantic-validated return value.

### Key design contracts

- **Orchestrator owns control flow; stages own prompting; LLM owns reasoning.** No branching logic inside stage files.
- **Schemas are the cross-stage contract.** All types are in `revere_agent/schemas/`. Every model has `extra="forbid"` so Pydantic emits `additionalProperties: false` for structured outputs.
- **Provider abstraction.** The codebase never sees a concrete model ID. Stages use logical aliases (`sonnet-main`, `haiku-fast`) resolved by the provider. `AnthropicProvider` maps these to `claude-sonnet-4-5` / `claude-haiku-4-5`. Bedrock is a second provider, structurally identical.
- **All prompts are versioned markdown files** in `revere_agent/prompts/`. The registry hashes them at load time and stores the hash in each `StageTraceEntry.prompt_version` so trace entries are tied to exact prompt text.

### UI

- `revere_agent/ui/gradio_app.py`: `build_demo()` constructs the Gradio layout. `run_chat_turn()` is the streaming generator: it spins the orchestrator in a background thread and yields progress updates every 250 ms.
- `revere_agent/ui/trace_renderer.py`: Pure rendering — converts `TurnResult` + `ProgressEvent` list into HTML/Markdown strings for each Gradio `gr.Markdown` panel. No business logic here.
- `revere_agent/ui/theme.css`: Custom dark-console visual theme. CSS variables are in `:root`; `.revere-*` classes are the component vocabulary.

### Current run modes (UI checkboxes)

| Mode | What changes |
|------|-------------|
| Full Audit (default) | 7 stages, all `sonnet-main`, max 6 hits |
| Fast mode | Same stages, max 4 hits — `fast_mode` checkbox |
| No Search | Same stages, Tavily disabled — `no_search` checkbox |

`haiku-fast` alias exists in the provider but is not yet routed to any stage.

### Stage latency profile (typical)

Each LLM stage takes 8–15 s on `sonnet-main`. With 7 stages + 2–3 Tavily calls, full-audit runs are typically 80–140 s. Out-of-scope short-circuits at S2 still take ~15–20 s because S1+S2 both use Sonnet.

### Tests

Tests are in `tests/`. They mock the orchestrator and LLM — no live API calls. Key helpers:
- `tests/test_trace_renderer.py` exports `_out_of_scope_turn_result()` and `_full_turn_result()` used by both test files.
- `test_gradio_app.py` patches `_build_orchestrator` to inject a mock orchestrator.
