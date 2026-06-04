# Revere — Auditable Political-Events Reasoning Agent

Revere is a political-reasoning agent designed around inspectability. Every query runs a fixed seven-stage pipeline. Each stage produces a Pydantic-validated structured output that can be read independently of the final answer — scope decision, search plan, per-source quality assessments, multi-perspective synthesis, claim verification, and a seven-point neutrality self-check.

The design avoids two common failure modes in AI-assisted political information: **authority fabrication** (presenting contested claims with the same confidence as established facts) and **keyword-based scope control** (deciding boundary cases by pattern-matching words in the query). Scope decisions and neutrality enforcement are delegated entirely to typed LLM stage outputs, keeping the reasoning visible and auditable.

## Pipeline

```text
User message
     │
  [S1] Intake ── normalise query; resolve cross-turn referents; classify modality
     │
  [S2] Scope ── reason against charter; produce in_scope and reasoning text
     │   └── in_scope=False → short-circuit (S3–S7 do not run)
     │
  [S3] Search Plan ── decide whether retrieval adds value; formulate ≤3 queries
     │   └── needs_search=True → Tavily API (concurrent, deduped, ≤6 hits)
     │
  [S4] Source Quality ── per-source assessment; emit EvidenceCoverage
     │
  [deterministic] EvidenceSufficiency ── derived from S4; no LLM call;
     │   propagated as binding constraint into S5, S6, S7
     │
  [S5] Perspectives ── steelman each view; rate evidence_coverage per perspective
     │
  [S6] Verification ── decompose claims; tag claim_type and support_level
     │
  [S7] Compose + Check ── draft answer; run 7-point SelfCheckReport; emit citations
```

Stages S1 and S3 run on a faster model (Haiku); S2, S4, S5, S6, and S7 run on Sonnet. Scope decisions stay on the stronger model because a false out-of-scope refusal on a valid political question is a failure mode that no latency saving justifies.

## Tech stack

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Pydantic — strict schema validation for every stage output (`extra="forbid"`)
- Anthropic API (Claude models); AWS Bedrock also supported via provider abstraction
- Tavily API — web search for freshness and evidence grounding
- FastAPI + Server-Sent Events — streaming backend
- Next.js — frontend with live stage trace and per-stage inspector panels
- Gradio — lightweight all-in-one local UI

## Running

### Gradio UI (standalone)

```bash
uv run revere-ui
# → http://localhost:7860
```

### Next.js UI + FastAPI backend

```bash
# Terminal 1
uv run revere-api          # → http://localhost:8000

# Terminal 2
cd web
npm install                # first time only
npm run dev                # → http://localhost:3000
```

The Next.js dev server proxies `/api/*` to `http://localhost:8000` — no CORS configuration needed.

## Environment variables

Copy `.env.example` to `.env`:

```
ANTHROPIC_API_KEY=...
TAVILY_API_KEY=...
```

`TAVILY_API_KEY` is optional. Without it, S3 will plan queries but search execution is skipped and the agent falls back to model knowledge with appropriate hedging.

## Tests

```bash
uv run pytest -q    # 224 tests; no API calls required
```

Tests cover orchestrator stage sequencing and short-circuit behavior, `EvidenceSufficiency` derivation and constraint injection, multi-turn history propagation, S7 input compaction, parallel search ordering and deduplication, schema validation, and the FastAPI layer. These are structural regression tests — they verify pipeline mechanics, not behavioral quality.

## Behavioral evaluation

The `evals/` directory contains a behavioral evaluation harness adapted from Anthropic's paired-prompt political-neutrality methodology. It is not a reproduction of the Anthropic benchmark; scenarios, judge prompts, and thresholds are specific to this project.

The harness runs the agent on six scenario groups across neutral and paired-prompt framings, captures the full stage trace as YAML fixtures, and evaluates each fixture with LLM judges on four dimensions: even-handedness, perspective quality, source grounding, and boundary handling.

```bash
# Generate fixtures (requires API keys; ~20 min with search enabled):
uv run python -m evals.generate_fixtures --all

# Evaluate existing fixtures with LLM judges:
uv run python -m evals.run_evals --mode fixtures --judge

# Eval structural tests (no API calls):
uv run pytest tests/test_evals.py tests/test_eval_fixtures.py tests/test_generate_fixtures.py -q
```

See `docs/EVAL_METHODOLOGY.md` for methodology and `docs/pipeline_guide.md` for expected pipeline behavior per scenario.

## Known limitations

**No repair-search loop.** When S4 finds weak or asymmetric evidence, `EvidenceSufficiency` restricts downstream claims rather than triggering a second search. The system flags the gap but does not attempt to fill it.

**Self-report bias.** The `SelfCheckReport` is produced by the same model that wrote the answer. The behavioral eval harness provides external validation through independent LLM judges, but those judges have their own failure modes — notably, they cannot distinguish correct asymmetric hedging (when real-world evidence bases are unequal) from framing bias.

**Retrieval freshness.** Tavily's free tier may not surface very recent articles for fast-moving stories.

**No mid-stage streaming.** SSE progress events fire on stage completion, not during token generation.

**Token limits in long sessions.** Multi-turn history is passed verbatim to S1; long sessions eventually approach token limits.
