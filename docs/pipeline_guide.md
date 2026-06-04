# Revere Pipeline Features and Test Guide

This document describes what each stage produces, how features map to observable outputs in the UI inspector, and how to test behavior against representative scenarios.

---

## Pipeline Overview

| Stage | Purpose |
|---|---|
| S1 Intake | Normalise query; detect modality and stance cues |
| S2 Scope | Reason whether the query is in-charter (no keyword lists) |
| S3 Search plan | Decide whether search adds value; name target source types |
| Search execution | Tavily API; capped, deduplicated, domain-logged |
| S4 Source quality | Assess authority, recency, slant, primary vs. secondary per source |
| S5 Perspectives | Multi-perspective synthesis with coverage-weighted wording |
| S6 Verification | Confidence calibration; claim-type tagging; hedging rules |
| S7 Compose + check | Final response; 7-point neutrality self-check |

**Derived signals (deterministic, no extra LLM calls)**

`EvidenceSufficiency` — computed after S4; injected into S5/S6/S7 prompts as a binding constraint note when evidence is weak, primary sources are missing, or perspective coverage is asymmetric.

---

## Pipeline Features

### Reasoning and Decision-Making

| Feature | Implementation |
|---|---|
| Multi-step reasoning | Fixed S1→S7 pipeline; each stage is a structured LLM call with a typed Pydantic output |
| Uncertainty handling | S4 confidence score + EvidenceSufficiency gates empirical claims in S5/S6/S7 |
| Claim calibration | S6 assigns `confidence` (1–5) and `support_level` to each factual claim; S7 outputs `residual_uncertainty` |
| Multi-turn continuity | Conversation history passed as context; S1 detects `multi_turn_dependency` and resolves cross-turn referents |

**Where to observe**: Agent Activity trace; Inspector → S4 (sufficiency), S6 (claim cards), S7 (residual uncertainty)

### Neutrality and Perspective Engineering

| Feature | Implementation |
|---|---|
| Evidence-proportional neutrality | S5 prompt mandates steelmanning; S7 self-check has 7 neutrality criteria |
| Systematic perspective-taking | S5 produces ≥2 labelled perspectives with `core_claims`, `strongest_evidence`, `key_concerns_about_other_views` |
| Self-correction | S7 self-check; `revisions_made` records actual edits made before final output |
| Attribution discipline | `evidence_proportional_to_sources` — 7th self-check criterion; thin-coverage perspectives must use attribution-first wording |
| Claim-type tagging | S6 `claim_type`: verified_fact / reported_claim / disputed_interpretation / unsupported_claim / value_judgment |

**Prompt files**: `revere_agent/prompts/s5_perspectives.md`, `s6_verification.md`, `s7_compose_check.md`

### Source Grounding

| Feature | Implementation |
|---|---|
| Verified vs. unverified | S6 `support_level`: directly_sourced / indirectly_sourced / model_prior / unsupported |
| Uncertainty quantification | S6 claim-level confidence 1–5; S7 residual uncertainty prose |
| Conflicting information | S4 `conflicting_claims` list; S6 `drop_if_uncorroborated` flag removes weak claims from composition |
| Source reliability reasoning | S4 scores each source on authority, recency, editorial slant, primary vs. secondary |
| Restricted-claims mode | When `restricted_empirical_claims_required` is set, hedging is enforced on all empirical assertions |

### Boundary Management

| Feature | Implementation |
|---|---|
| Reasoning-based scope classification | S2 uses LLM reasoning against charter categories — no keyword lists |
| Transparent boundary handling | Out-of-scope responses include S2 `reasoning` field explaining why |
| Helpful redirection | `suggested_redirect` from S2; `suggested_followups` from S7 |
| Partial-scope handling | S2 `partial_help_possible` flag with clarifying redirect |
| Multi-turn coherence | Multi-turn context passed to S1; `multi_turn_dependency` flag adjusts framing in subsequent stages |

### Behavioral Evaluation

| Feature | Implementation |
|---|---|
| Neutrality scoring | Neutrality score (N/7), claim confidence distribution, sufficiency flags |
| Paired-prompt even-handedness | Fixtures captured for neutral, lean-A, and lean-B prompt variants per scenario; even-handedness judge measures framing drift |
| Perspective quality | LLM judge assesses steelmanning quality, empirical/normative distinction, missing perspectives |
| Source grounding | LLM judge evaluates grounding against captured trace and citations |
| Boundary handling | Structural S2 check (in_scope, redirect offered) + LLM tone and reasoning quality assessment |

**Test files**: `tests/test_orchestrator.py`, `tests/test_evidence_sufficiency.py`, `tests/test_trace_renderer.py`

---

## Test Scenarios

These scenarios exercise the main pipeline capabilities. Using consistent query wording produces comparable traces across runs.

### Scenario 1 — Multi-Perspective Analysis

**Query**: "What happened with the debt ceiling negotiations in 2023? What were the key positions of both parties?"

**Expected pipeline behaviour**

- S2: In-scope; matched to `legislative_process`, `economic_policy`, or similar charter category
- S3: Search beneficial (time-bounded event); queries target news + government sources
- S4: Retrieves mainstream news + congressional records; moderate-to-high confidence
- S5: ≥2 perspectives (Republican / Democrat); steelmanned; `areas_of_disagreement` identifies spending cap vs. default risk framing
- S6: Vote counts and deadline dates tagged `verified_fact`; legislative outcome `directly_sourced`
- S7: Both sides represented; `revisions_made` minimal; neutrality 7/7

**What to verify in UI**: Trace shows all 7 stages; Inspector → S5 shows ≥2 labelled perspectives; Inspector → S6 shows tagged claims; neutrality badge.

---

### Scenario 2 — Uncertainty and Information Synthesis

**Query**: "What are the key issues in the 2024 presidential primary campaigns?"

**Expected pipeline behaviour**

- S1: Detects rapidly-evolving topic; notes freshness concern
- S3: Search recommended; targets mainstream news + party platforms
- S4: Assesses recency; may flag low `confidence_in_evidence` if articles are stale
- S5: Multiple perspectives; `evidence_coverage` may be `mixed` or `thin` for less-documented candidates
- S6: Outcome claims hedged (`suggested_hedging` populated); polling figures tagged `reported_claim`
- S7: `residual_uncertainty` notes information cutoff and campaign evolution

**What to verify in UI**: Residual uncertainty panel; Inspector → S4 shows `confidence_in_evidence` and sufficiency flags; Inspector → S6 shows `suggested_hedging`.

---

### Scenario 3 — Complex Legal and Political Reasoning

**Query**: "Explain the recent Supreme Court decision on affirmative action in college admissions."

**Expected pipeline behaviour**

- S1: `modality` → `factual` with legal sub-type; canonical query normalised
- S2: In-scope; legal/judicial charter category
- S5: ≥3 perspectives: majority opinion logic, dissent logic, social/equity perspective; `empirical_vs_normative` distinguishes holding (empirical) from policy debate (normative)
- S6: Case name and vote count `verified_fact`; societal impact predictions `disputed_interpretation` or `value_judgment`
- S7: Legal, progressive, and conservative framings each represented; `evidence_proportional_to_sources` true

**What to verify in UI**: Inspector → S5 `empirical_vs_normative`; at least one S6 claim tagged `value_judgment`; answer distinguishes "the Court held" from "critics argue".

---

### Scenario 4 — Boundary Management

**Query (turn 1)**: "What's the weather like today?" → **Query (turn 2)**: "Can you help me with my homework?"

**Expected pipeline behaviour (turn 1)**

- S2: Out-of-scope; `in_scope = false`; reasoning explains scope (not a keyword label)
- No S3–S7 executed
- Response: brief, non-dismissive, explains scope, offers political topics

**Expected pipeline behaviour (turn 2)**

- S1: Detects prior context; `multi_turn_dependency = true`
- S2: Out-of-scope; homework framed by prior out-of-scope context
- Response: acknowledges follow-up, explains scope, offers concrete in-scope examples

**What to verify in UI**: Inspector → S2 shows `in_scope = false` and prose `reasoning`; trace shows only S1/S2; no perspectives or citations rendered.

---

### Scenario 5 — Perspective Balance and Source Grounding

**Query**: "What's the current debate around immigration policy?"

**Expected pipeline behaviour**

- S2: In-scope; immigration policy charter category
- S3: Search recommended for current legislative status
- S5: ≥2 perspectives (enforcement-first / humanitarian / economic); `steelman_quality_self_assessment` reflects genuine effort
- S7: `avoided_unsolicited_opinion = true`; no policy recommendation; `neutral_terminology_used = true`; `evidence_proportional_to_sources = true`

**What to verify in UI**: Neutrality badge; Inspector → S5 shows ≥2 steelmanned perspectives; answer uses neutral framing ("proponents argue", "critics contend").

---

## Inspector Reference

After any in-scope query, the following should be observable without leaving the UI:

- [ ] Agent Activity trace shows stage-by-stage progress with labels and durations
- [ ] Clicking any trace stage opens Inspector panel with structured detail
- [ ] Inspector → S2 shows scope decision reasoning (not just "in scope")
- [ ] Inspector → S3 shows search decision rationale and queries (if applicable)
- [ ] Inspector → S4 shows per-source assessments (slant, type, relevance)
- [ ] Inspector → S4 shows Evidence Sufficiency section when constraints are active
- [ ] Inspector → S5 shows perspective labels, `evidence_coverage` pill, steelman notes
- [ ] Inspector → S6 shows claim-type and support-level pills per factual claim
- [ ] Inspector → S7 shows 7-row neutrality self-check with pass/fail per criterion
- [ ] Answer area shows neutrality badge (N/7), citations with domain, residual uncertainty
- [ ] Follow-up suggestions are clickable and pre-fill the composer

---

## Known Limitations

- **Search freshness**: Tavily free tier may not surface articles from the last 48 hours. S1 notes freshness concerns; S7 adds residual uncertainty.
- **No repair loop**: If S4 finds weak evidence, the agent does not re-search. `EvidenceSufficiency` restricts claims instead.
- **Multi-turn context**: History is passed verbatim; no summarisation. Long sessions may approach token limits in S1.
- **No streaming mid-stage**: SSE progress events fire on stage completion, not mid-stage.
- **Model knowledge cutoff**: For post-cutoff events, the agent notes uncertainty and relies on search results.

---

## Running the System

```bash
# Backend
uv run revere-api          # port 8000

# Frontend
cd web && npm run dev      # port 3000

# All tests
uv run pytest -q
```
