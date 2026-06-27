"""Core data models for the multi-agent paper-review system."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class Paper:
    """A parsed submission. Prefer LaTeX source over PDF (keeps math intact)."""
    paper_id: str
    title: str = ""
    abstract: str = ""
    sections: dict[str, str] = field(default_factory=dict)  # name -> text
    references: list[str] = field(default_factory=list)
    figures: list[dict] = field(default_factory=list)        # {caption, ref, ...}
    raw_text: str = ""
    source_format: str = "text"                              # latex | pdf | text | md
    meta: dict[str, Any] = field(default_factory=dict)

    def as_review_input(self, max_chars: int = 120_000) -> str:
        """Flatten to a single text blob suitable for an LLM review prompt."""
        parts = [f"# {self.title}", "", "## Abstract", self.abstract, ""]
        for name, text in self.sections.items():
            parts += [f"## {name}", text, ""]
        if self.references:
            parts += ["## References", "\n".join(self.references)]
        blob = "\n".join(p for p in parts if p is not None)
        return blob[:max_chars] if max_chars else blob


class Recommendation(str, Enum):
    ACCEPT = "accept"
    MINOR_REVISION = "minor_revision"
    MAJOR_REVISION = "major_revision"
    REJECT = "reject"
    DESK_REJECT = "desk_reject"


@dataclass
class DimensionReview:
    """One reviewer agent's verdict on one quality dimension."""
    dimension: str                       # novelty / soundness / experiments / ...
    score: float | None = None           # on the venue's rubric scale
    scale_max: float | None = None
    confidence: float | None = None      # 1-5
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)   # grounded quotes/refs
    raw: str = ""
    agent: str = ""
    model: str = ""


@dataclass
class VerificationResult:
    """Adversarial verification output (novelty/claim/code checks)."""
    target: str                          # which claim/dimension was checked
    verdict: str                         # supported | refuted | uncertain
    rationale: str = ""
    sources: list[str] = field(default_factory=list)
    changed_assessment: bool = False


@dataclass
class MetaReview:
    """Area-chair level aggregation."""
    summary: str = ""
    recommendation: Recommendation | None = None
    overall_score: float | None = None
    confidence: float | None = None
    disagreement: float | None = None    # variance across dimension reviews
    needs_human_review: bool = False
    key_strengths: list[str] = field(default_factory=list)
    key_concerns: list[str] = field(default_factory=list)
    actionable_revisions: list[str] = field(default_factory=list)


@dataclass
class ReviewReport:
    """Full output for one submission against one venue."""
    paper_id: str
    venue: str
    venue_match: dict[str, Any] = field(default_factory=dict)
    desk_screen: dict[str, Any] = field(default_factory=dict)
    dimension_reviews: list[DimensionReview] = field(default_factory=list)
    verifications: list[VerificationResult] = field(default_factory=list)
    meta_review: MetaReview | None = None
    quality_critique: dict[str, Any] = field(default_factory=dict)
    ai_detection: dict[str, Any] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)          # per-stage provenance
