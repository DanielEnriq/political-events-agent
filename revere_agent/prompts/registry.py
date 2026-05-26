"""Prompt loader and version registry.

Every prompt is a markdown file on disk. The registry:
  - loads them by stage_id
  - records the SHA1 of the file contents at load time

The hash is what each ReasoningTrace entry stores in `prompt_version`,
which means a behavior change visible in evals can be traced back to a
specific prompt edit. This is production discipline that Civic will need
for their drafting and message-review work — and it costs almost nothing
to add on Day 1.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

# Map stable stage IDs to the .md file that drives them.
_STAGE_TO_FILE: dict[str, str] = {
    "system_charter": "system_charter.md",
    "s1_intake": "s1_intake.md",
    "s2_scope": "s2_scope.md",
    "s3_plan_search": "s3_plan_search.md",
    "s4_source_quality": "s4_source_quality.md",
    "s5_perspectives": "s5_perspectives.md",
    "s6_verification": "s6_verification.md",
    "s7_compose_check": "s7_compose_check.md",
}


@lru_cache(maxsize=None)
def load_prompt(stage_id: str) -> str:
    filename = _STAGE_TO_FILE.get(stage_id)
    if not filename:
        raise KeyError(
            f"Unknown stage_id '{stage_id}'. Known: {sorted(_STAGE_TO_FILE)}"
        )
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def prompt_version(stage_id: str) -> str:
    """Short SHA1 of the prompt file, for trace metadata."""
    text = load_prompt(stage_id)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
