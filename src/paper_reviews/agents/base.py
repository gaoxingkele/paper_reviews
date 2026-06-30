"""Agent base class: a thin wrapper that turns a prompt pair into a parsed result.

All agents share JSON-constrained output + optional multi-provider voting.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from ..llm_client import chat, ChatResult, LLMCallError

logger = logging.getLogger("paper_reviews.agent")


def parse_json(text: str) -> dict:
    """Best-effort JSON extraction (models sometimes wrap in prose/fences)."""
    text = text.strip()
    # strip code fences
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        # grab the outermost {...}
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    logger.warning("JSON parse failed; returning raw under '_raw'")
    return {"_raw": text}


@dataclass
class AgentSpec:
    """Per-role model configuration (from config/agents.yaml)."""
    provider: str = "claude"
    reasoning: bool = False
    temperature: float = 0.3
    voters: int = 1                 # >1 = multi-sample / multi-provider voting
    extra_providers: list[str] = field(default_factory=list)
    fallbacks: list[str] = field(default_factory=list)  # tried when a provider's chain is exhausted


def _chat_with_fallback(providers: list[str], system_prompt: str, user_prompt: str,
                        *, who: str, **kw) -> ChatResult:
    """Call the first healthy provider; on LLMCallError move to the next.

    Implements the cross-provider degradation the llm_client docstring delegates
    to the agent layer: a provider's whole model chain may be down (gateway
    flakiness, model not provisioned), so we fall through to a healthy one rather
    than dropping the dimension entirely.
    """
    last_err: Exception | None = None
    seen: set[str] = set()
    for provider in providers:
        p = (provider or "").strip().lower()
        if not p or p in seen:
            continue
        seen.add(p)
        try:
            return chat(p, system_prompt, user_prompt, **kw)
        except LLMCallError as e:
            last_err = e
            logger.warning("[%s] provider %s unavailable; falling back: %s", who, p, e)
    raise LLMCallError(f"[{who}] all providers failed: {last_err}")


class Agent:
    def __init__(self, name: str, spec: AgentSpec | None = None):
        self.name = name
        self.spec = spec or AgentSpec()

    def run(self, system_prompt: str, user_prompt: str,
            *, response_json: bool = True) -> tuple[dict, ChatResult]:
        res = _chat_with_fallback(
            [self.spec.provider, *self.spec.fallbacks],
            system_prompt,
            user_prompt,
            who=self.name,
            reasoning=self.spec.reasoning,
            temperature=self.spec.temperature,
            response_json=response_json,
        )
        return parse_json(res.text), res

    def run_voting(self, system_prompt: str, user_prompt: str) -> list[tuple[dict, ChatResult]]:
        """Run across providers/samples for robustness (returns all ballots)."""
        providers = [self.spec.provider] + self.spec.extra_providers
        ballots: list[tuple[dict, ChatResult]] = []
        rounds = max(self.spec.voters, len(providers))
        for i in range(rounds):
            provider = providers[i % len(providers)]
            # each voter prefers its assigned provider, then the shared fallbacks
            chain = [provider, *self.spec.fallbacks]
            try:
                res = _chat_with_fallback(chain, system_prompt, user_prompt,
                                          who=f"{self.name}#voter{i}",
                                          reasoning=self.spec.reasoning,
                                          temperature=self.spec.temperature + 0.1 * i,
                                          response_json=True)
                ballots.append((parse_json(res.text), res))
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] voter %d (%s) failed: %s", self.name, i, provider, e)
        return ballots
