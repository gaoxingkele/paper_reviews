"""Cloubic routing helpers for OpenAI-compatible LLM calls.

Ported from the ``news-monitor`` project. Cloubic (https://cloubic.com) is a
unified gateway that exposes 100+ models behind one OpenAI-compatible API key,
reachable from mainland China without a proxy.

Behaviour:
- optionally load ``.env.cloubic``
- route whitelisted providers via Cloubic (others stay direct)
- expose per-provider model chains for fallback / reasoning variants
"""
from __future__ import annotations

import os
from pathlib import Path

_CLOUBIC_LOADED = False


def _project_root() -> Path:
    # src/paper_reviews/cloubic.py -> paper_reviews -> src -> <root>
    return Path(__file__).resolve().parents[2]


def load_cloubic_env() -> None:
    """Load ``.env.cloubic`` from the project root if present (idempotent)."""
    global _CLOUBIC_LOADED
    if _CLOUBIC_LOADED:
        return

    env_path = _project_root() / ".env.cloubic"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:
                os.environ[key] = value

    _CLOUBIC_LOADED = True


def cloubic_enabled() -> bool:
    load_cloubic_env()
    return (
        os.getenv("CLOUBIC_ENABLED", "").strip().lower() == "true"
        and bool(os.getenv("CLOUBIC_API_KEY", "").strip())
    )


def should_route_via_cloubic(provider: str) -> bool:
    if not cloubic_enabled():
        return False
    provider = (provider or "").strip().lower()
    if not provider:
        return False
    whitelist = os.getenv("CLOUBIC_ROUTED_PROVIDERS", "").strip()
    if not whitelist:
        return True
    allowed = {x.strip().lower() for x in whitelist.split(",") if x.strip()}
    return provider in allowed


def get_cloubic_base_url() -> str:
    load_cloubic_env()
    return os.getenv(
        "CLOUBIC_BASE_URL", "https://api.cloubic.com/v1/chat/completions"
    ).strip()


def get_cloubic_api_key() -> str:
    load_cloubic_env()
    return os.getenv("CLOUBIC_API_KEY", "").strip()


def get_cloubic_model_chain(provider: str, *, reasoning: bool = False) -> list[str]:
    """Return the configured Cloubic model chain (best -> fallback) for a provider."""
    load_cloubic_env()
    provider = (provider or "").strip().upper()
    if not provider:
        return []
    keys: list[str] = []
    if reasoning:
        keys.append(f"CLOUBIC_{provider}_REASONING_MODEL")
    keys.append(f"CLOUBIC_{provider}_MODEL")
    for key in keys:
        raw = os.getenv(key, "").strip()
        if raw:
            return [x.strip() for x in raw.split(",") if x.strip()]
    return []


def resolve_openai_compatible_endpoint(
    provider: str,
    *,
    direct_api_key: str,
    direct_base_url: str,
    direct_model: str,
    reasoning: bool = False,
) -> tuple[str, str, list[str], bool]:
    """Resolve (api_key, base_url, model_chain, via_cloubic) for a chat call."""
    if should_route_via_cloubic(provider):
        model_chain = get_cloubic_model_chain(provider, reasoning=reasoning) or [direct_model]
        return get_cloubic_api_key(), get_cloubic_base_url(), model_chain, True
    return direct_api_key, direct_base_url, [direct_model], False
