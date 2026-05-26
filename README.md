# Political Events Agent
A small AI chatbot prototype for neutral, grounded discussion of political events.
This project is being built for the Civic LLM Engineer candidacy project. The goal is to demonstrate agentic reasoning, political neutrality, hallucination prevention, conversational boundary management, and evaluation of chatbot behavior.
## Goals
The chatbot should:
- answer political-event questions with balanced, multi-perspective analysis;
- use search/information tools when factual grounding is needed;
- distinguish verified facts, uncertainty, and interpretation;
- avoid partisan framing and unsupported claims;
- handle out-of-scope requests gracefully;
- avoid keyword-based classification or canned responses;
- include tests/evals for required scenarios.
## Required Scenarios
1. Debt ceiling negotiations in 2023.
2. 2024 presidential primary campaigns.
3. Supreme Court affirmative action decision.
4. Out-of-scope requests like weather or homework help.
5. Current immigration policy debate.
## Planned Architecture
```text
User Query
    ↓
Request Understanding
    ↓
Scope + Information Need Decision
    ↓
Search Tool or Direct Reasoning
    ↓
Evidence Assessment
    ↓
Multi-Perspective Synthesis
    ↓
Neutrality / Uncertainty Check
    ↓
Final Response

Tech Stack

Planned:

- Python
- Gradio
- Pydantic
- Anthropic or OpenAI
- Tavily or similar search API
- Pytest/scripted evals

Project Structure

political-events-agent/
  src/
    agent/
      prompts.py
      schemas.py
      tools.py
      chatbot.py
    evals/
      scenarios.py
      run_evals.py
    app.py
  docs/
    assignment.md
    design_notes.md
  tests/
  README.md
  .env.example
  pyproject.toml

Design Principles

- No keyword-based political classification.
- No hardcoded bias-word lists.
- No template-based political responses.
- Use reasoning-based scope and boundary management.
- Use tools for factual grounding when needed.
- Express uncertainty instead of overclaiming.
- Keep responses neutral, useful, and conversational.

Setup

uv sync
uv run python src/app.py

Environment Variables

Create a .env file from .env.example:

ANTHROPIC_API_KEY=
OPENAI_API_KEY=
TAVILY_API_KEY=

Deliverables

- Working chatbot agent.
- Simple local web interface.
- Evaluation suite for required scenarios.
- Technical notes explaining design decisions.
- Loom demo showing all required scenarios.

Status

Initial setup. Implementation in progress.