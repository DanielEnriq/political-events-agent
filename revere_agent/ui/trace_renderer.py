"""Render ReasoningTrace + TurnResult into readable HTML/Markdown for the Gradio panel."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from revere_agent.agent.orchestrator import ProgressEvent, SearchExecutionStats, TurnResult

STAGE_TITLES: dict[str, str] = {
    "s1_intake": "S1 — Intake",
    "s2_scope": "S2 — Scope",
    "s3_plan_search": "S3 — Search Plan",
    "search_execution": "Search",
    "s4_source_quality": "S4 — Evidence",
    "s5_perspectives": "S5 — Perspectives",
    "s6_verification": "S6 — Verification",
    "s7_compose_check": "S7 — Compose & Self-Check",
}

# All stages collapsed inside the trace section — reader expands what they want
STAGE_DETAILS_DEFAULT_OPEN: set[str] = set()
STAGE_DETAILS_DEFAULT_COLLAPSED: set[str] = {
    "s1_intake",
    "s2_scope",
    "s3_plan_search",
    "s4_source_quality",
    "s5_perspectives",
    "s6_verification",
    "s7_compose_check",
}


@dataclass
class UIRunOptions:
    fast_mode: bool = False
    no_search: bool = False
    max_hits: int = 6


def _esc(text: str) -> str:
    return html.escape(str(text))


def _card(title: str, body: str, *, css_class: str = "revere-card") -> str:
    if not body.strip():
        return ""
    return (
        f'<div class="{css_class}">'
        f'<div class="revere-card-header">{_esc(title)}</div>'
        f'<div class="revere-card-body">{body}</div>'
        f"</div>"
    )


def _details_card(title: str, body: str) -> str:
    """Card that starts collapsed — user clicks to expand."""
    if not body.strip():
        return ""
    return (
        f'<details class="revere-details-card">\n'
        f'<summary class="revere-details-summary">{_esc(title)}</summary>\n'
        f'<div class="revere-details-card-body">{body}</div>\n'
        f'</details>\n'
    )


def _badge(text: str, kind: str = "neutral") -> str:
    return f'<span class="revere-badge revere-badge-{kind}">{_esc(text)}</span>'


def _details(title: str, body: str, *, open_by_default: bool = False) -> str:
    if not body.strip():
        return ""
    open_attr = " open" if open_by_default else ""
    return (
        f"<details{open_attr}>\n"
        f"<summary>{_esc(title)}</summary>\n\n{body}\n\n</details>\n\n"
    )


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc or url
        return host.removeprefix("www.")
    except Exception:  # noqa: BLE001
        return url


def compute_mode_label(fast_mode: bool, no_search: bool) -> str:
    """Single-source mode label used in badge, chat progress, and tests."""
    if fast_mode and no_search:
        return "Fast Audit · No Search"
    if no_search:
        return "No Search"
    if fast_mode:
        return "Fast Audit"
    return "Full Audit"


def _mode_label(options: UIRunOptions) -> str:
    return compute_mode_label(options.fast_mode, options.no_search)


def render_mode_banner(options: UIRunOptions) -> str:
    """Compact single-line mode badge."""
    label = compute_mode_label(options.fast_mode, options.no_search)
    if options.no_search:
        detail = "Model knowledge only — no retrieved sources."
        kind = "neutral"
    elif options.fast_mode:
        detail = f"Faster run · max {options.max_hits} sources."
        kind = "accent"
    else:
        detail = f"Complete audit · max {options.max_hits} sources · typically 60–120 s."
        kind = "accent"
    return (
        f'<div class="revere-mode-badge">'
        f'<span class="revere-badge revere-badge-{kind}">{_esc(label)}</span>'
        f'<span class="revere-mode-detail">{_esc(detail)}</span>'
        f'</div>'
    )


def render_stage_compact_summary(stage_id: str, output: dict[str, Any]) -> str:
    """One-line summary for a completed stage."""
    if stage_id == "s1_intake":
        return (
            f"Canonical query: {output.get('canonical_query', '')}\n"
            f"Modality: {output.get('modality', '')}"
        )
    if stage_id == "s2_scope":
        categories = output.get("matched_charter_categories") or []
        cat_str = ", ".join(categories) if categories else "(none)"
        in_scope = output.get("in_scope")
        scope_label = "in scope" if in_scope else "out of scope"
        return (
            f"{scope_label.title()} · confidence {output.get('confidence')}/5\n"
            f"Categories: {cat_str}"
        )
    if stage_id == "s3_plan_search":
        needs = output.get("needs_search")
        q_count = len(output.get("queries") or [])
        return f"Needs search: {needs} · {q_count} planned quer{'y' if q_count == 1 else 'ies'}"
    if stage_id == "s4_source_quality":
        n = len(output.get("assessments") or [])
        conf = output.get("confidence_in_evidence")
        return f"{n} source assessment(s) · evidence confidence {conf}/5"
    if stage_id == "s5_perspectives":
        n = len(output.get("perspectives") or [])
        return f"{n} perspective(s) mapped"
    if stage_id == "s6_verification":
        n = len(output.get("claims") or [])
        return f"{n} factual claim(s) calibrated"
    if stage_id == "s7_compose_check":
        check = output.get("neutrality_self_check") or {}
        passed = sum(
            1
            for key in (
                "avoided_unsolicited_opinion",
                "factually_accurate_and_comprehensive",
                "steelmanned_each_perspective",
                "neutral_terminology_used",
                "equal_depth_across_perspectives",
                "respectful_tone",
            )
            if check.get(key)
        )
        return f"Self-check: {passed}/6 principles satisfied"
    return ""


def format_progress_event(event: ProgressEvent) -> str:
    """Format one progress event for the live timeline (legacy format — kept for tests)."""
    css = "revere-timeline-item"
    if event.status == "started":
        css += " is-active"
    elif event.status == "completed":
        css += " is-complete"
    elif event.status == "stopped":
        css += " is-stopped"

    parts = [
        f'<div class="{css}">',
        f'<div class="revere-timeline-title">{_esc(event.message)}</div>',
    ]

    if event.status == "completed" and event.output:
        summary = render_stage_compact_summary(event.stage_id, event.output)
        if summary:
            parts.append(
                f'<div class="revere-timeline-summary">'
                f'{_esc(summary).replace(chr(10), "<br>")}'
                f'</div>'
            )

    if event.stage_id == "search_execution" and event.extra:
        extra = event.extra
        parts.append(
            '<div class="revere-timeline-summary">'
            f"Calls: {extra.get('search_calls_made', 0)} · "
            f"Raw hits: {extra.get('raw_hits', 0)} · "
            f"Unique: {extra.get('unique_hits', 0)} · "
            f"Passed to S4: {extra.get('hits_passed_to_s4', 0)}"
            "</div>"
        )

    if event.duration_ms is not None:
        parts.append(
            f'<div class="revere-timeline-timing">{event.duration_ms:,} ms</div>'
        )

    parts.append("</div>")
    return "".join(parts)


def _render_timeline_row(
    stage_id: str,
    state: dict[str, Any],
) -> str:
    """Render one folded stage row for the new compact timeline."""
    status = state["status"]
    css = "revere-timeline-row"
    if status == "started":
        css += " is-active"
    elif status == "completed":
        css += " is-complete"
    elif status == "stopped":
        css += " is-stopped"

    # Status indicator
    if status == "started":
        dot = '<span class="revere-timeline-dot"></span>'
    elif status == "completed":
        dot = '<span class="revere-timeline-dot-done">✓</span>'
    elif status == "stopped":
        dot = '<span class="revere-timeline-dot-stop">—</span>'
    else:
        dot = '<span class="revere-timeline-dot-pending">·</span>'

    title = STAGE_TITLES.get(stage_id, stage_id)

    dur = state.get("duration_ms")
    dur_html = (
        f'<span class="revere-timeline-timing">{dur:,} ms</span>' if dur is not None else ""
    )

    # Compact one-liner summary
    summary_html = ""
    output = state.get("output")
    if output and status == "completed":
        raw = render_stage_compact_summary(stage_id, output)
        if raw:
            # Collapse newlines into " · " for a single line
            one_line = raw.replace("\n", " · ")
            summary_html = (
                f'<div class="revere-timeline-summary">{_esc(one_line)}</div>'
            )

    # Search execution extra info
    if stage_id == "search_execution" and state.get("extra") and status == "completed":
        ex = state["extra"]
        summary_html = (
            f'<div class="revere-timeline-summary">'
            f'Calls: {ex.get("search_calls_made", 0)} · '
            f'Raw: {ex.get("raw_hits", 0)} · '
            f'Unique: {ex.get("unique_hits", 0)} · '
            f'To S4: {ex.get("hits_passed_to_s4", 0)}'
            f'</div>'
        )

    return (
        f'<div class="{css}">'
        f'<div class="revere-timeline-left">{dot}</div>'
        f'<div class="revere-timeline-content">'
        f'<div class="revere-timeline-title">{_esc(title)}{" " + dur_html if dur_html else ""}</div>'
        f'{summary_html}'
        f'</div>'
        f'</div>'
    )


def render_timeline_markdown(
    events: list[ProgressEvent],
    *,
    options: UIRunOptions | None = None,
    running: bool = False,
) -> str:
    """Folded pipeline timeline — one row per stage, no duplicate start/complete entries."""
    options = options or UIRunOptions()

    if not events and not running:
        return _card(
            "Pipeline Timeline",
            '<p class="revere-empty">Timeline appears here as stages run.</p>',
        )

    # Fold events into per-stage state (last event for each stage wins)
    stage_states: dict[str, dict[str, Any]] = {}
    stage_order: list[str] = []

    for event in events:
        sid = event.stage_id
        if sid not in stage_states:
            stage_states[sid] = {
                "status": event.status,
                "message": event.message,
                "output": event.output,
                "duration_ms": event.duration_ms,
                "stage_num": event.stage_num,
                "extra": event.extra,
            }
            stage_order.append(sid)
        else:
            s = stage_states[sid]
            s["status"] = event.status
            if event.output is not None:
                s["output"] = event.output
            if event.duration_ms is not None:
                s["duration_ms"] = event.duration_ms
            if event.extra is not None:
                s["extra"] = event.extra

    parts: list[str] = []
    if running:
        parts.append('<p class="revere-timeline-running">Pipeline running…</p>')

    for sid in stage_order:
        parts.append(_render_timeline_row(sid, stage_states[sid]))

    return _card("Pipeline Timeline", "".join(parts))


def _timing_lines(result: TurnResult) -> tuple[list[str], int]:
    lines: list[str] = []
    total_ms = 0
    for entry in result.trace.entries:
        total_ms += entry.duration_ms
        label = STAGE_TITLES.get(entry.stage_id, entry.stage_id)
        lines.append(
            f"{_badge(label, 'accent')} "
            f'<span class="revere-timeline-timing">{entry.duration_ms:,} ms</span>'
        )
    lines.append(
        f"<strong>Total LLM stage time:</strong> "
        f'<span class="revere-timeline-timing">{total_ms:,} ms</span>'
    )
    return lines, total_ms


def _render_run_summary(result: TurnResult, options: UIRunOptions, total_ms: int) -> str:
    return (
        f"<p>{_badge(_mode_label(options))} {_badge(f'max hits {options.max_hits}', 'neutral')}</p>"
        f"<p><strong>Turn ID:</strong> <code>{_esc(result.trace.turn_id)}</code></p>"
        f"<p><strong>Started:</strong> {_esc(result.trace.started_at.isoformat())}</p>"
        f"<p><strong>Stages completed:</strong> {len(result.trace.entries)}</p>"
        f"<p><strong>In scope:</strong> {'yes' if result.scope.in_scope else 'no'}</p>"
        f"<p><strong>Total LLM stage time:</strong> {total_ms:,} ms</p>"
    )


def _render_search_summary(result: TurnResult) -> str:
    stats: SearchExecutionStats | None = result.search_stats
    if stats is None:
        return '<p class="revere-muted">Search not run (pipeline stopped before planning).</p>'

    used = result.search_executed or stats.search_calls_made > 0
    lines = [
        f"<p><strong>Search used:</strong> {'yes' if used else 'no'}</p>",
        f"<p><strong>S3 queries:</strong> {stats.s3_queries}</p>",
        f"<p><strong>Search calls:</strong> {stats.search_calls_made}</p>",
        f"<p><strong>Raw hits:</strong> {stats.raw_hits}</p>",
        f"<p><strong>Unique after dedup:</strong> {stats.unique_hits_after_dedup}</p>",
        f"<p><strong>Passed to S4:</strong> {stats.hits_passed_to_s4}</p>",
        f"<p><strong>Results capped:</strong> {'yes' if stats.results_capped else 'no'}</p>",
    ]
    if result.search_hits:
        lines.append("<p><strong>URLs passed to S4:</strong></p><ul>")
        for hit in result.search_hits:
            lines.append(
                f'<li><a href="{_esc(hit.url)}" target="_blank">{_esc(hit.domain)}</a></li>'
            )
        lines.append("</ul>")
    return "".join(lines)


def _render_s1(output: dict[str, Any]) -> str:
    return (
        f"<p><strong>Canonical query:</strong> {_esc(output.get('canonical_query', ''))}</p>"
        f"<p>{_badge(str(output.get('modality', '')), 'accent')}</p>"
        f"<p class='revere-muted'>{_esc(output.get('notes', ''))}</p>"
    )


def _render_s2(output: dict[str, Any]) -> str:
    categories = output.get("matched_charter_categories") or []
    in_scope = output.get("in_scope")
    scope_badge = _badge("in scope", "ok") if in_scope else _badge("out of scope", "warn")
    cat_badges = " ".join(_badge(c, "neutral") for c in categories) or _badge("(none)", "neutral")
    conf_val = output.get("confidence")
    lines = [
        f"<p>{scope_badge} {_badge(f'confidence {conf_val}/5', 'accent')}</p>",
        f"<p><strong>Categories:</strong> {cat_badges}</p>",
        f"<p class='revere-muted'>{_esc(output.get('reasoning', ''))}</p>",
    ]
    redirect = output.get("suggested_redirect")
    if redirect:
        lines.append(f"<p><strong>Suggested redirect:</strong> {_esc(redirect)}</p>")
    return "".join(lines)


def _render_s3(output: dict[str, Any]) -> str:
    queries = output.get("queries") or []
    query_items = "".join(f"<li>{_esc(q)}</li>" for q in queries) or "<li>(none)</li>"
    types = output.get("target_source_types") or []
    return (
        f"<p><strong>Needs search:</strong> {output.get('needs_search')}</p>"
        f"<p class='revere-muted'>{_esc(output.get('rationale', ''))}</p>"
        f"<p><strong>Queries:</strong></p><ul>{query_items}</ul>"
        f"<p><strong>Target source types:</strong> "
        f"{_esc(', '.join(types) if types else '(none)')}</p>"
    )


def _render_s4(output: dict[str, Any]) -> str:
    ev_conf = output.get("confidence_in_evidence")
    lines = [
        f"<p>{_badge(f'evidence confidence {ev_conf}/5', 'accent')}</p>"
    ]
    assessments = output.get("assessments") or []
    if assessments:
        for i, a in enumerate(assessments, start=1):
            lines.append(
                '<div class="revere-source-card">'
                f'<div class="revere-source-index">[{i}]</div>'
                "<div>"
                f'<div class="revere-source-title">'
                f'<a href="{_esc(a.get("url", ""))}" target="_blank">'
                f'{_esc(a.get("source_type", "source"))}</a></div>'
                f'<div class="revere-source-domain">'
                f'{_esc(_domain_from_url(a.get("url", "")))}</div>'
                f'<div class="revere-source-used">'
                f'relevance {a.get("relevance_to_query")}/5 · '
                f'confidence {a.get("confidence_in_source")}/5 · '
                f'{_esc(a.get("authority_reasoning", ""))}'
                f"</div></div></div>"
            )
    else:
        lines.append('<p class="revere-empty">No retrieved sources (model-knowledge path).</p>')

    conflicts = output.get("conflicting_claims") or []
    if conflicts:
        lines.append("<p><strong>Conflicting claims:</strong></p><ul>")
        lines.extend(f"<li>{_esc(c)}</li>" for c in conflicts)
        lines.append("</ul>")

    gaps = output.get("gaps") or []
    if gaps:
        lines.append("<p><strong>Gaps:</strong></p><ul>")
        lines.extend(f"<li>{_esc(g)}</li>" for g in gaps)
        lines.append("</ul>")
    return "".join(lines)


def _render_s5(output: dict[str, Any]) -> str:
    lines: list[str] = []
    for p in output.get("perspectives") or []:
        lines.append(f"<p><strong>{_esc(p.get('label', 'perspective'))}</strong></p>")
        lines.append("<ul>")
        lines.extend(f"<li>{_esc(c)}</li>" for c in p.get("core_claims") or [])
        lines.append("</ul>")

    consensus = output.get("areas_of_consensus") or []
    if consensus:
        lines.append("<p><strong>Consensus:</strong></p><ul>")
        lines.extend(f"<li>{_esc(c)}</li>" for c in consensus)
        lines.append("</ul>")

    disagreement = output.get("areas_of_disagreement") or []
    if disagreement:
        lines.append("<p><strong>Disagreement:</strong></p><ul>")
        lines.extend(f"<li>{_esc(d)}</li>" for d in disagreement)
        lines.append("</ul>")
    return "".join(lines) if lines else '<p class="revere-empty">No perspectives recorded.</p>'


def _render_s6(output: dict[str, Any]) -> str:
    lines = [
        f"<p class='revere-muted'>{_esc(output.get('overall_calibration_note', ''))}</p>"
    ]
    for c in output.get("claims") or []:
        conf = c.get("confidence")
        badge_kind = "ok" if conf and conf >= 4 else "warn" if conf and conf >= 3 else "neutral"
        lines.append(
            '<div class="revere-claim-card">'
            f'<div class="revere-claim-text">{_esc(c.get("claim", ""))}</div>'
            f'<div class="revere-claim-meta">'
            f'{_badge(f"confidence {conf}/5", badge_kind)} '
            f'{_badge(str(c.get("verification_basis", "")), "neutral")}'
            f"</div></div>"
        )

    avoid = output.get("things_i_should_not_assert") or []
    if avoid:
        lines.append("<p><strong>Do not assert:</strong></p><ul>")
        lines.extend(f"<li>{_esc(a)}</li>" for a in avoid)
        lines.append("</ul>")
    return "".join(lines)


def _render_s7(output: dict[str, Any]) -> str:
    check = output.get("neutrality_self_check") or {}
    principles = [
        ("Avoided unsolicited opinion", check.get("avoided_unsolicited_opinion")),
        ("Factually accurate & comprehensive", check.get("factually_accurate_and_comprehensive")),
        ("Steelmanned perspectives", check.get("steelmanned_each_perspective")),
        ("Neutral terminology", check.get("neutral_terminology_used")),
        ("Equal depth", check.get("equal_depth_across_perspectives")),
        ("Respectful tone", check.get("respectful_tone")),
    ]
    badges = " ".join(_badge(name, "ok" if ok else "warn") for name, ok in principles)
    lines = [
        f"<p>{badges}</p>",
        f"<p class='revere-muted'><strong>Residual uncertainty:</strong> "
        f"{_esc(output.get('residual_uncertainty', ''))}</p>",
    ]
    revisions = check.get("revisions_made") or []
    if revisions:
        lines.append("<p><strong>Revisions:</strong></p><ul>")
        lines.extend(f"<li>{_esc(r)}</li>" for r in revisions)
        lines.append("</ul>")
    return "".join(lines)


def _render_source_cards(result: TurnResult) -> str:
    """Compact citation cards — one line per source."""
    final = result.final_response or result.trace.final_response
    if final is None or not final.citations:
        return (
            '<p class="revere-empty">'
            "No citations — no retrieved sources or none used in the final answer."
            "</p>"
        )

    parts: list[str] = []
    for i, c in enumerate(final.citations, start=1):
        domain = _domain_from_url(c.url)
        claim_short = (
            c.used_for_claim[:80] + "…"
            if len(c.used_for_claim) > 80
            else c.used_for_claim
        )
        parts.append(
            f'<div class="revere-source-card-compact">'
            f'<div class="revere-source-index">[{i}]</div>'
            f'<div class="revere-source-body">'
            f'<div class="revere-source-title">'
            f'<a href="{_esc(c.url)}" target="_blank">{_esc(c.label)}</a>'
            f'</div>'
            f'<div class="revere-source-domain">{_esc(domain)}</div>'
            f'<div class="revere-source-used">{_esc(claim_short)}</div>'
            f'</div>'
            f'</div>'
        )
    return "".join(parts)


def render_final_answer_panel(result: TurnResult) -> str:
    """Primary user-facing answer card."""
    if not result.scope.in_scope:
        redirect = result.scope.suggested_redirect or (
            "This request is outside the agent's scope for US political events."
        )
        body = (
            f'<p class="revere-final-answer">{_esc(redirect)}</p>'
            '<p class="revere-muted">Boundary response — pipeline stopped after scope check (S2).</p>'
        )
        return _card("Final Answer", body)

    final = result.final_response or result.trace.final_response
    if final is None:
        return _card(
            "Final Answer",
            '<p class="revere-empty">Pipeline completed without a final response.</p>',
        )

    body = f'<div class="revere-final-answer">{_esc(final.response_text)}</div>'
    if final.residual_uncertainty:
        body += (
            f'<p class="revere-muted" style="margin-top:0.75rem">'
            f"<strong>Residual uncertainty:</strong> {_esc(final.residual_uncertainty)}</p>"
        )
    return _card("Final Answer", body)


def render_trust_panel(result: TurnResult) -> str:
    """Compact verification summary — calibration note + neutrality badge only."""
    if not result.scope.in_scope:
        return _card(
            "Trust & Verification",
            '<p class="revere-muted">Not applicable — request was out of scope.</p>',
        )

    parts: list[str] = []

    # S6 calibration note only (no per-claim cards in the top panel)
    for entry in result.trace.entries:
        if entry.stage_id == "s6_verification":
            note = entry.output.get("overall_calibration_note", "")
            if note:
                parts.append(f'<p class="revere-muted">{_esc(note)}</p>')
            not_assert = entry.output.get("things_i_should_not_assert") or []
            if not_assert:
                parts.append(
                    f'<p class="revere-muted">'
                    f"<em>{len(not_assert)} claim(s) excluded or hedged.</em>"
                    f"</p>"
                )
            break

    # S7 neutrality self-check badge
    final = result.final_response or result.trace.final_response
    if final is not None:
        check = final.neutrality_self_check
        passed = sum([
            check.avoided_unsolicited_opinion,
            check.factually_accurate_and_comprehensive,
            check.steelmanned_each_perspective,
            check.neutral_terminology_used,
            check.equal_depth_across_perspectives,
            check.respectful_tone,
        ])
        badge_kind = "ok" if passed >= 5 else "warn"
        parts.append(f'<p>{_badge(f"Neutrality self-check {passed}/6", badge_kind)}</p>')

    if not parts:
        return _card("Trust & Verification", '<p class="revere-empty">Verification pending…</p>')

    return _card("Trust & Verification", "".join(parts))


def render_citations_markdown(result: TurnResult) -> str:
    """Compact sources panel."""
    return _card("Sources", _render_source_cards(result))


def render_timing_markdown(result: TurnResult) -> str:
    lines, _ = _timing_lines(result)
    body = "".join(f"<p>{line}</p>" for line in lines)
    return _card("Timing Summary", body)


def render_search_budget_markdown(result: TurnResult) -> str:
    return _card("Search Budget", _render_search_summary(result))


def _render_stage_sections(result: TurnResult) -> str:
    renderers = {
        "s1_intake": _render_s1,
        "s2_scope": _render_s2,
        "s3_plan_search": _render_s3,
        "s4_source_quality": _render_s4,
        "s5_perspectives": _render_s5,
        "s6_verification": _render_s6,
        "s7_compose_check": _render_s7,
    }
    parts: list[str] = []
    for entry in result.trace.entries:
        title = STAGE_TITLES.get(entry.stage_id, entry.stage_id)
        renderer = renderers.get(entry.stage_id)
        compact = render_stage_compact_summary(entry.stage_id, entry.output)
        detail_body = (
            renderer(entry.output)
            if renderer
            else f"<pre>{_esc(json.dumps(entry.output, indent=2))}</pre>"
        )
        timing = (
            f'<span class="revere-timeline-timing">{entry.duration_ms:,} ms</span> '
            f'<span class="revere-muted">prompt `{_esc(entry.prompt_version)}`</span>'
        )
        summary_block = f"<p>{_esc(compact).replace(chr(10), '<br>')}</p><p>{timing}</p>"
        # All stage cards collapsed — let reader expand what they want
        parts.append(
            _details(
                f"{title} ({entry.duration_ms:,} ms)",
                summary_block + detail_body,
                open_by_default=False,
            )
        )
    return "".join(parts)


def render_trace_markdown(
    result: TurnResult,
    *,
    options: UIRunOptions | None = None,
    include_raw_json: bool = False,
) -> str:
    """Full reasoning trace — collapsed by default, audit-oriented."""
    options = options or UIRunOptions()
    timing_lines, total_ms = _timing_lines(result)

    inner_parts: list[str] = [
        '<div class="revere-panel-markdown">',
        _details("Run Summary", _render_run_summary(result, options, total_ms), open_by_default=True),
    ]

    if not result.scope.in_scope:
        inner_parts.append(
            '<p class="revere-muted"><strong>Boundary short-circuit:</strong> '
            "pipeline stopped after S2 (out of scope).</p>"
        )

    inner_parts.append(
        _details("Search Overview", _render_search_summary(result), open_by_default=False)
    )
    inner_parts.append(
        _details("Stage Trace", _render_stage_sections(result), open_by_default=False)
    )
    inner_parts.append(
        _details(
            "Timing Breakdown",
            "".join(f"<p>{line}</p>" for line in timing_lines),
            open_by_default=False,
        )
    )

    if include_raw_json:
        inner_parts.append(
            _details(
                "Raw trace JSON",
                f"<pre>{_esc(result.trace.model_dump_json(indent=2))}</pre>",
                open_by_default=False,
            )
        )

    inner_parts.append("</div>")
    body = "".join(inner_parts)

    return _card("Reasoning Trace", body)


def render_answer_support(
    state: str,
    *,
    options: UIRunOptions | None = None,
    events: list[ProgressEvent] | None = None,
    result: TurnResult | None = None,
    error_message: str | None = None,
    include_raw_trace: bool = False,
) -> str:
    """Unified right-panel renderer.

    State must be one of: 'empty', 'running', 'completed', 'error'.
    Returns a single HTML string for one gr.Markdown output — no tuple mismatch.
    """
    opts = options or UIRunOptions()
    evts = events or []
    parts: list[str] = [render_mode_banner(opts)]

    if state == "empty":
        parts.append(
            '<p class="revere-support-hint">Ask a question to see answer support.</p>'
        )

    elif state == "running":
        parts.append(render_timeline_markdown(evts, options=opts, running=True))
        ph = '<p class="revere-empty">In progress…</p>'
        parts.append(_card("Sources", ph))
        parts.append(_card("Trust &amp; Verification", ph))

    elif state == "completed" and result is not None:
        parts.append(render_citations_markdown(result))
        parts.append(render_trust_panel(result))
        parts.append(render_timeline_markdown(evts, options=opts, running=False))
        parts.append(render_timing_markdown(result))
        parts.append(
            render_trace_markdown(result, options=opts, include_raw_json=include_raw_trace)
        )

    elif state == "error":
        msg = error_message or "An unexpected error occurred."
        parts.append(_card("Error", f'<p class="revere-muted">{_esc(msg)}</p>'))

    return "\n".join(p for p in parts if p)
