"""Configuration loading: journal profiles + agent/model mapping.

A *journal profile* (config/journals/<venue>.yaml) is the first-class input that
makes a review targeted and level-matched. The orchestrator reads it to decide
which dimension agents to run, on what rubric, with what strictness, calibrated
to the venue's score distribution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
JOURNALS_DIR = ROOT / "config" / "journals"
AGENTS_CONFIG = ROOT / "config" / "agents.yaml"


@dataclass
class RubricDimension:
    key: str                       # novelty / soundness / experiments / ...
    label: str
    description: str = ""
    scale_max: float = 10.0
    weight: float = 1.0
    enabled: bool = True
    strictness: float = 1.0        # multiplier; >1 = harsher
    agent: str = ""                # which reviewer agent handles it (defaults to key)


@dataclass
class JournalProfile:
    venue: str
    full_name: str = ""
    aims_scope: str = ""
    level: str = "standard"        # top / strong / standard / regional
    decision_threshold: float = 6.0
    score_distribution: dict[str, float] = field(default_factory=dict)  # for calibration
    dimensions: list[RubricDimension] = field(default_factory=list)
    policies: dict[str, Any] = field(default_factory=dict)              # AI use, ethics, length
    exemplars: list[dict] = field(default_factory=list)                # few-shot anchors
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def enabled_dimensions(self) -> list[RubricDimension]:
        return [d for d in self.dimensions if d.enabled]


def load_journal(venue: str) -> JournalProfile:
    """Load a journal profile by file stem (e.g. 'ieee_access')."""
    path = JOURNALS_DIR / f"{venue}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No journal profile: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    dims = []
    for d in data.get("dimensions", []):
        dims.append(RubricDimension(
            key=d["key"],
            label=d.get("label", d["key"]),
            description=d.get("description", ""),
            scale_max=float(d.get("scale_max", 10.0)),
            weight=float(d.get("weight", 1.0)),
            enabled=bool(d.get("enabled", True)),
            strictness=float(d.get("strictness", 1.0)),
            agent=d.get("agent", d["key"]),
        ))

    return JournalProfile(
        venue=data.get("venue", venue),
        full_name=data.get("full_name", ""),
        aims_scope=data.get("aims_scope", ""),
        level=data.get("level", "standard"),
        decision_threshold=float(data.get("decision_threshold", 6.0)),
        score_distribution=data.get("score_distribution", {}) or {},
        dimensions=dims,
        policies=data.get("policies", {}) or {},
        exemplars=data.get("exemplars", []) or [],
        extra=data.get("extra", {}) or {},
    )


def list_journals() -> list[str]:
    if not JOURNALS_DIR.is_dir():
        return []
    return sorted(p.stem for p in JOURNALS_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def load_agents_config() -> dict[str, Any]:
    """Map agent role -> {provider, reasoning, temperature, voters, ...}."""
    if not AGENTS_CONFIG.is_file():
        return {}
    return yaml.safe_load(AGENTS_CONFIG.read_text(encoding="utf-8")) or {}
