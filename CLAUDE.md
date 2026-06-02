# CLAUDE.md

Project instructions for Claude Code.

## Project identity

This repository contains Revere — Agentic Political Events AI Chatbot, a Civic LLM Engineer candidacy project.

This is not a generic chatbot or UI-only project. It is a reasoning-agent evaluation. The project must demonstrate:

- multi-step chatbot-agent reasoning;
- political neutrality and balanced perspective-taking;
- hallucination prevention through uncertainty and source-quality reasoning;
- conversational intelligence and boundary management;
- behavior evaluation for reasoning quality, neutrality, and scope control.

The UI exists to demonstrate the agent’s reasoning. Do not optimize the UI in ways that hide or bypass the reasoning architecture.

## Submission requirements

The final submission must include:

1. GitHub repository with complete source code and documentation.
2. A simple local web interface for testing the chatbot agent.
3. Loom demo showing all 5 required scenarios working.

Required demo scenarios:

1. 2023 debt ceiling negotiations and both parties’ positions.
2. 2024 presidential primary campaign issues.
3. Supreme Court affirmative action decision.
4. Weather / homework boundary-management scenario.
5. Current immigration policy debate.

## Immediate failure criteria

Never introduce:

- keyword-based political classification;
- hardcoded political keyword lists;
- regex/string-matching scope control;
- rule-based bias detection with biased-word lists;
- template-based political answers;
- scripted answers for the required scenarios;
- search/database lookup as a replacement for reasoning.

Bad patterns:

python POLITICAL_KEYWORDS = ["election", "vote", "congress"] BIAS_KEYWORDS = ["liberal", "conservative"]  if "weather" in query:     refuse() 

The assignment explicitly tests reasoning and prompt engineering, not keyword matching.

## Core architecture

The Python S1–S7 pipeline is the source of truth.

Stages:

- S1 Intake / context normalization
- S2 Scope reasoning
- S3 Search planning
- Search execution
- S4 Source-quality reasoning
- S5 Multi-perspective synthesis
- S6 Verification / confidence calibration
- S7 Final response + neutrality self-check

Do not bypass these stages for political answers unless explicitly asked to implement a separate fast mode. Even in fast mode, preserve reasoning-based scope control, source-awareness, uncertainty handling, and neutrality.

## Backend constraints

Do not change these unless explicitly requested:

- prompt semantics in revere_agent/prompts/;
- Pydantic schemas in revere_agent/schemas/;
- S1–S7 stage contracts;
- orchestrator semantics;
- LLM provider abstractions;
- Tavily/search abstraction;
- CLI behavior.

If backend changes are necessary:

- keep them small;
- update tests;
- explain which rubric requirement the change supports.

## Frontend direction

Preferred UI model:

- one primary chat stream;
- assistant message contains a live Agent Activity trace;
- final answer appears below the completed trace;
- right panel, if present, is an inspector for clicked trace stages;
- no giant dashboard competing with chat;
- no fragile dropdown-heavy trace in the main flow;
- dark charcoal palette, muted text, cream/warm accent.

The frontend should make these visible:

- scope decision and reasoning;
- search decision;
- source-quality assessment;
- perspectives considered;
- verification/calibration;
- neutrality self-check;
- residual uncertainty.

The UI should not reimplement reasoning in TypeScript. The Python backend remains the source of truth.

## Streaming requirements

The Next.js UI uses a FastAPI SSE backend.

Streaming path:

- FastAPI /chat streams start, progress, complete, and error events.
- Next.js /api/chat route handler proxies the stream without buffering.
- Frontend parses SSE events and updates the active assistant message.
- Progress events update the live Agent Activity trace.
- Complete event fills in final answer, citations, verification summary, and trace.

Do not reintroduce Next.js rewrites for /api/chat; rewrites caused SSE buffering.

If streaming breaks:

1. Verify backend directly:
   bash    curl -N -X POST http://localhost:8000/chat \      -H "Content-Type: application/json" \      -d '{"message":"What happened with the debt ceiling negotiations in 2023?","fast_mode":true,"skip_search":true,"max_hits":3,"raw_trace":false}'    

2. Verify Next proxy:
   bash    curl -N -X POST http://localhost:3000/api/chat \      -H "Content-Type: application/json" \      -d '{"message":"What happened with the debt ceiling negotiations in 2023?","fast_mode":true,"skip_search":true,"max_hits":3,"raw_trace":false}'    

3. Fix parser/state before doing visual polish.

## State management guidance

For streamed frontend work:

- use functional React state updates;
- avoid stale closures;
- keep the active assistant message as the source of truth;
- append progress events to that assistant message;
- on complete, update the same assistant message with the final result;
- on error, update the same assistant message with the error.

Do not keep trace state, panel state, and message state as unrelated sources of truth unless there is a clear reason.

## Development process

Use small phases. Do not combine backend, frontend, styling, evals, and docs in one patch.

Preferred order:

1. Fix correctness and streaming.
2. Make trace visible in chat.
3. Add right-hand inspector.
4. Add localStorage chat list/sidebar.
5. Polish visuals.
6. Finish eval harness and docs.

When asked for a large feature, first inspect and plan. Wait for approval before editing unless the user explicitly says to implement.

Subagents may be used for inspection/review, but the main agent should make final edits. Do not let multiple subagents independently rewrite overlapping files.

## Commands

Run Python tests:

bash uv run pytest -q 

Run FastAPI backend:

bash uv run revere-api 

Alternative:

bash uv run uvicorn api.server:app --port 8000 

Run Next.js frontend:

bash cd web npm run dev 

Build Next.js frontend:

bash cd web npm run build 

Verify FastAPI import:

bash uv run python -c "from api.server import app; print(app.title)" 

## Manual demo checks

Before calling the project demo-ready, manually test:

1. What's the weather like today?
   - Should show scope reasoning and graceful boundary handling.

2. What happened with the debt ceiling negotiations in 2023? What were the key positions of both parties?
   - Should show balanced perspectives, sources, verification, uncertainty.

3. What are the key issues in the 2024 presidential primary campaigns?
   - Should search or acknowledge freshness concerns.

4. Explain the recent Supreme Court decision on affirmative action in college admissions.
   - Should distinguish legal, political, and social perspectives.

5. What's the current debate around immigration policy?
   - Should show balanced perspective-taking and source-grounding.

## Commit hygiene

Never commit:

- .env
- API keys
- local debug logs
- throwaway output files

Usually safe to commit:

- api/
- web/
- revere_agent/
- tests/
- README.md
- pyproject.toml
- uv.lock
- .env.example
- CLAUDE.md

## Reporting format

After making changes, report:

- changed files;
- tests run and results;
- exact launch commands;
- what rubric/project requirement the change supports;
- limitations or risks;
- anything deferred.

Keep reports concise and factual.