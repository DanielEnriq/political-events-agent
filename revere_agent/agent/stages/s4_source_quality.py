"""Stage 4 — Source-Quality Reasoning.

Two modes (the stage prompt knows about both):
  Mode A: search was performed. We pass the hits; the LLM produces per-source
          assessments + an aggregate EvidenceBase.
  Mode B: search was NOT performed. We pass an explicit "no-search" notice;
          the LLM produces a minimal EvidenceBase that documents the
          model-knowledge limitation in its `gaps` field.

Mode B exists because downstream stages (S5) need an EvidenceBase regardless
of whether retrieval ran — and making the limitation explicit in the trace
is a project requirement.
"""

from __future__ import annotations

from revere_agent.llm.provider import LLMProvider
from revere_agent.schemas import EvidenceBase, ExtractedDoc, IntakeAnalysis, SearchHit

from ._common import run_llm_stage

_S4_SNIPPET_CHAR_LIMIT = 360


def _format_hits(hits: list[SearchHit], extracted: list[ExtractedDoc]) -> str:
    """Render hits compactly. Extracted full content is appended if present."""
    extracted_by_url = {d.url: d.raw_content for d in extracted}
    lines: list[str] = []
    for i, h in enumerate(hits, start=1):
        date = h.published_date or "unknown"
        lines.append(
            f"[{i}] {h.title}\n"
            f"    URL:       {h.url}\n"
            f"    Domain:    {h.domain}\n"
            f"    Published: {date}\n"
            f"    Snippet:   {h.snippet[:_S4_SNIPPET_CHAR_LIMIT]}"
        )
        if h.url in extracted_by_url:
            # Truncate aggressively so we don't blow the context window with
            # raw HTML-ish content. S4 is judgment, not extraction.
            content = extracted_by_url[h.url][:2000]
            lines.append(f"    Extracted: {content}")
    return "\n\n".join(lines) if lines else "(no hits)"


def run_s4_source_quality(
    provider: LLMProvider,
    intake: IntakeAnalysis,
    hits: list[SearchHit],
    extracted: list[ExtractedDoc] | None = None,
    *,
    search_was_performed: bool,
) -> EvidenceBase:
    """Build an EvidenceBase from the hits, or document the no-search case."""
    extracted = extracted or []

    if search_was_performed:
        user_content = (
            f"Canonical query:\n{intake.canonical_query}\n\n"
            f"Retrieved sources ({len(hits)} hit(s)):\n\n{_format_hits(hits, extracted)}\n\n"
            "Apply the Source-Quality Reasoning instructions above "
            "(Case A: sources were retrieved). Return an EvidenceBase."
        )
    else:
        user_content = (
            f"Canonical query:\n{intake.canonical_query}\n\n"
            "Stage 3 determined that no external search was necessary; "
            "this answer relies on the model's training knowledge.\n\n"
            "Apply the Source-Quality Reasoning instructions above "
            "(Case B: no search was performed). Return a lightweight "
            "EvidenceBase that documents this limitation in its `gaps` field."
        )

    return run_llm_stage(
        provider=provider,
        stage_id="s4_source_quality",
        user_content=user_content,
        output_schema=EvidenceBase,
    )
