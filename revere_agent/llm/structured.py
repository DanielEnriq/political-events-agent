"""Structured-output helper with a beta-first / tool-use-fallback strategy.

Two paths, in order:

1. **Native structured outputs (beta).** Anthropic shipped a structured-
   outputs beta (header `structured-outputs-2025-11-13`, exposed in recent
   SDKs via `client.beta.messages.parse(...)` or an equivalent helper).
   When available, this is the most direct path: pass a Pydantic class,
   get back a parsed instance.

2. **Forced tool-use (the safety net).** Tool-use has been GA in the
   Anthropic API for a long time. We register a single tool whose
   `input_schema` is the Pydantic JSON Schema, then force the model to
   call it with `tool_choice={'type': 'tool', 'name': ...}`. The tool's
   `input` is guaranteed by the API to validate against the schema, and
   we run it through `model_validate` for final type safety.

The fallback exists because Anthropic's structured-outputs beta interface
has churned and may differ across SDK versions. The reasoning pipeline
should never be blocked by SDK details — and tool-use does the same job.
"""

from __future__ import annotations

from typing import Any, TypeVar

from anthropic import Anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# The beta header for native structured outputs, per Anthropic docs (Nov 2025).
STRUCTURED_OUTPUTS_BETA = "structured-outputs-2025-11-13"


def call_with_structured_output(
    client: Anthropic,
    *,
    model: str,
    system: str,
    user: str,
    output_schema: type[T],
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> T:
    """Return a Pydantic-validated instance of `output_schema`.

    Tries native structured outputs first; on any failure, falls back to
    forced tool-use. Both paths return the same Python object.
    """
    try:
        return _native_structured_outputs(
            client,
            model=model,
            system=system,
            user=user,
            output_schema=output_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception:  # noqa: BLE001 — any beta-path failure → fallback
        # We deliberately swallow here. The tool-use fallback is the
        # supported, GA route, and it does the same job. Failures specific
        # to the beta SDK shape should not block the pipeline.
        return _forced_tool_use(
            client,
            model=model,
            system=system,
            user=user,
            output_schema=output_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def _native_structured_outputs(
    client: Anthropic,
    *,
    model: str,
    system: str,
    user: str,
    output_schema: type[T],
    temperature: float,
    max_tokens: int,
) -> T:
    """Path 1: Anthropic's native structured outputs (beta).

    Probes the most likely API shape. If the SDK doesn't expose it (older
    SDK, breaking beta change), we raise and the caller falls back.
    """
    beta_messages = getattr(getattr(client, "beta", None), "messages", None)
    parse_fn = getattr(beta_messages, "parse", None) if beta_messages else None

    if parse_fn is None:
        raise NotImplementedError(
            "client.beta.messages.parse not available in this SDK build"
        )

    response = parse_fn(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
        response_format=output_schema,
        betas=[STRUCTURED_OUTPUTS_BETA],
    )

    # Different SDK builds expose the parsed object under different names.
    parsed = (
        getattr(response, "parsed", None)
        or getattr(response, "output_parsed", None)
    )
    if parsed is None:
        raise ValueError("Native structured-outputs response had no parsed payload")

    return (
        parsed
        if isinstance(parsed, output_schema)
        else output_schema.model_validate(parsed)
    )


def _forced_tool_use(
    client: Anthropic,
    *,
    model: str,
    system: str,
    user: str,
    output_schema: type[T],
    temperature: float,
    max_tokens: int,
) -> T:
    """Path 2: forced tool-use — reliable, GA, schema-validated.

    Register one tool whose input_schema is the Pydantic JSON Schema, then
    force the model to call it. Parse the tool's `input` as the schema.
    """
    schema: dict[str, Any] = output_schema.model_json_schema()
    tool_name = f"emit_{output_schema.__name__}"

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[
            {
                "name": tool_name,
                "description": (
                    f"Emit a structured {output_schema.__name__} object. "
                    "This is the ONLY way to respond. Fill every required "
                    "field carefully; do not invent extra fields."
                ),
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return output_schema.model_validate(block.input)

    raise RuntimeError(
        f"Model did not return the forced tool '{tool_name}'. "
        f"Stop reason: {getattr(response, 'stop_reason', 'unknown')}"
    )
