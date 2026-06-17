"""tracelens quickstart — no LLM required.

Runs the @traced decorator over a faked LLM call so you can see traces flow
into the collector without spending any tokens.

Usage:
    docker compose up -d
    python examples/quickstart.py
    open http://localhost:8000
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

import tracelens


@dataclass
class FakeUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class FakeMessage:
    content: str


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeChatResponse:
    """Mimics the shape of openai.chat.completions.create()'s return value."""

    choices: list[FakeChoice]
    usage: FakeUsage
    model: str


MODELS = [
    ("gpt-4o-mini", 0.85, 150),
    ("gpt-4o", 1.4, 240),
    ("claude-3-5-sonnet", 1.1, 220),
    ("claude-3-5-haiku", 0.6, 90),
]

PROMPTS = [
    "Summarize the latest commit in two sentences.",
    "Draft a one-line release note for the new dashboard.",
    "Translate this support reply into formal Spanish.",
    "Generate three eval rubrics for a customer-support chatbot.",
    "What are likely causes of a 3x cost spike in the last 24 hours?",
]


def fake_chat(prompt: str, model: str, base_latency_s: float, base_completion_tokens: int) -> FakeChatResponse:
    # Sleep to mimic latency variance.
    time.sleep(base_latency_s * (0.6 + random.random() * 0.9))
    if random.random() < 0.05:
        raise RuntimeError("simulated upstream timeout")
    prompt_tokens = max(8, len(prompt.split()))
    completion_tokens = base_completion_tokens + random.randint(-40, 60)
    return FakeChatResponse(
        choices=[FakeChoice(message=FakeMessage(content=f"[{model}] reply to: {prompt}"))],
        usage=FakeUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        model=model,
    )


def run() -> None:
    tracelens.configure(endpoint="http://localhost:8000", print_local=True)
    print("Posting 25 synthetic traces to http://localhost:8000 …")
    for _ in range(25):
        model, latency, ctokens = random.choice(MODELS)
        prompt = random.choice(PROMPTS)

        @tracelens.traced(model=model, capture_prompt=False, capture_completion=False)
        def call(p: str = prompt) -> FakeChatResponse:
            return fake_chat(p, model, latency, ctokens)

        try:
            call()
        except Exception as exc:  # noqa: BLE001
            print(f"  → caught simulated error: {exc}")
    # Give the daemon threads a beat to flush.
    time.sleep(1.0)
    print("Done. Open http://localhost:8000 to see the dashboard.")


if __name__ == "__main__":
    run()
