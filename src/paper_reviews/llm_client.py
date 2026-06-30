"""Multi-provider OpenAI-compatible chat client with Cloubic routing + fallback.

Design goals
------------
- One ``chat()`` entry point keyed by a logical *provider* name
  (claude / gemini / openai / deepseek / qwen / glm / grok / kimi / doubao).
- When Cloubic is enabled and the provider is whitelisted, the call is routed
  through Cloubic with the configured model-degradation chain. Otherwise the
  provider is called directly (its own key/base-url, optional proxy).
- The chain is tried best -> worst; on exhaustion the caller may fall back to a
  different provider (handled at the agent/orchestrator layer).

This is deliberately synchronous (httpx.Client) so review pipelines stay easy to
script, debug, and run from cron.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .cloubic import resolve_openai_compatible_endpoint

logger = logging.getLogger("paper_reviews.llm")

# --- direct-connection defaults per provider (used when NOT routed via Cloubic) ---
# (api_key_env, base_url_env, base_url_default, model_env, model_default, use_proxy)
_DIRECT: dict[str, dict] = {
    "deepseek": dict(key="DEEPSEEK_API_KEY", base="DEEPSEEK_BASE_URL",
                     base_default="https://api.deepseek.com/v1",
                     model_default="deepseek-chat", proxy=False),
    "kimi":     dict(key="KIMI_API_KEY", base="KIMI_BASE_URL",
                     base_default="https://api.moonshot.cn/v1",
                     model_default="moonshot-v1-128k", proxy=False),
    "qwen":     dict(key="QWEN_API_KEY", base="QWEN_BASE_URL",
                     base_default="https://dashscope.aliyuncs.com/compatible-mode/v1",
                     model_default="qwen-long", proxy=False),
    "doubao":   dict(key="DOUBAO_API_KEY", base="DOUBAO_BASE_URL",
                     base_default="https://ark.cn-beijing.volces.com/api/v3",
                     model_default="doubao-seed-1-6-flash-250828", proxy=False),
    "grok":     dict(key="GROK_API_KEY", base="GROK_BASE_URL",
                     base_default="https://api.x.ai/v1",
                     model_default="grok-4-1-fast-reasoning", proxy=True),
    # claude / gemini / openai / glm are expected to go through Cloubic.
}

_ENV_LOADED = False


def load_env() -> None:
    """Load ``.env`` (and let cloubic module load ``.env.cloubic``)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k and k not in os.environ:
                os.environ[k] = v
    _ENV_LOADED = True


class LLMCallError(RuntimeError):
    pass


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str
    via_cloubic: bool
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0


def _endpoint_url(base_url: str) -> str:
    """Normalise a base url to a full chat/completions endpoint."""
    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return base_url + "/chat/completions"


def chat(
    provider: str,
    system_prompt: str,
    user_prompt: str,
    *,
    reasoning: bool = False,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    timeout: float = 600.0,
    retries: int = 2,
    response_json: bool = False,
) -> ChatResult:
    """Call ``provider`` and return the assistant text.

    Tries the Cloubic model-degradation chain (or the single direct model) in
    order; raises :class:`LLMCallError` only when every model fails.
    """
    load_env()
    # env overrides so batch runs can cap hang time (gateway can wedge sockets)
    _t = os.getenv("PR_LLM_TIMEOUT", "").strip()
    if _t:
        try: timeout = float(_t)
        except ValueError: pass
    _r = os.getenv("PR_LLM_RETRIES", "").strip()
    if _r:
        try: retries = int(_r)
        except ValueError: pass
    provider = provider.strip().lower()
    direct = _DIRECT.get(provider, {})

    direct_api_key = os.getenv(direct.get("key", ""), "").strip() if direct else ""
    direct_base = os.getenv(direct.get("base", ""), "").strip() if direct else ""
    direct_base = direct_base or direct.get("base_default", "")
    direct_model = direct.get("model_default", provider)

    api_key, base_url, model_chain, via_cloubic = resolve_openai_compatible_endpoint(
        provider,
        direct_api_key=direct_api_key,
        direct_base_url=direct_base,
        direct_model=direct_model,
        reasoning=reasoning,
    )

    if not api_key:
        raise LLMCallError(f"[{provider}] missing API key (cloubic={via_cloubic})")

    use_proxy = (not via_cloubic) and bool(direct.get("proxy"))
    proxy = os.getenv("LLM_PROXY", "").strip() if use_proxy else ""
    client_kwargs: dict = {"timeout": httpx.Timeout(timeout), "trust_env": False,
                           "follow_redirects": True}
    if proxy:
        client_kwargs["proxy"] = proxy

    url = _endpoint_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_err: Exception | None = None
    with httpx.Client(**client_kwargs) as client:
        for model in model_chain:
            payload: dict = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens
            if response_json:
                payload["response_format"] = {"type": "json_object"}

            for attempt in range(retries + 1):
                t0 = time.time()
                try:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code >= 400:
                        raise LLMCallError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"]
                    return ChatResult(
                        text=text, provider=provider, model=model,
                        via_cloubic=via_cloubic, usage=data.get("usage", {}),
                        latency_s=round(time.time() - t0, 2),
                    )
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    logger.warning("[%s/%s] attempt %d failed: %s",
                                   provider, model, attempt + 1, e)
                    if attempt < retries:
                        time.sleep(1.5 * (attempt + 1))
            logger.warning("[%s] model %s exhausted, trying next in chain", provider, model)

    raise LLMCallError(f"[{provider}] all models failed: {last_err}")
