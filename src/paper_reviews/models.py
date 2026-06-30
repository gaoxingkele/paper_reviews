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
        """Flatten to a single text blob suitable for an LLM review prompt.

        Falls back to ``raw_text`` when section parsing produced nothing (typical
        for PDFs, which have no markdown/latex structure markers) — otherwise the
        manuscript body would be dropped from the review input.
        """
        if not self.sections:
            parts = []
            if self.title:
                parts.append(f"# {self.title}")
            body = self.raw_text or self.abstract
            parts.append(body)
            if self.references and "References" not in body[-2000:]:
                parts += ["", "## References", "\n".join(self.references)]
            blob = "\n".join(parts)
            return blob[:max_chars] if max_chars else blob
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
class Finding:
    """One atomic, evidence-grounded reviewer finding (ported from review_simulator).

    Carries the quantitative fields the deterministic risk scorer needs
    (severity/confidence/fixability) plus the qualitative fields that make the
    output actionable (reviewer_voice/evidence/fix_suggestion). ``journal_sensitivity``
    lets ONE finding be scored differently across journals; ``hard_gate`` marks an
    IEEE-Access binary-veto trigger.
    """
    dimension: str                       # novelty / soundness / experiments / ...
    severity: float = 0.0                # 0 none .. 4 fatal
    confidence: float = 0.0              # 0..1
    fixability: float = 0.5             # 0 (redo experiments) .. 1 (rewrite only)
    issue: str = ""
    reviewer_voice: str = ""            # original-words-level reviewer comment
    evidence: str = ""                  # location/quote in the manuscript
    journal_sensitivity: str = ""       # how severity shifts across journals
    hard_gate: bool = False             # suspected IEEE-Access one-veto trigger
    fix_suggestion: str = ""


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
    findings: list[Finding] = field(default_factory=list)
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
class RiskScore:
    """Per-journal acceptance-risk index (ported from review_simulator RRI).

    Computed deterministically in scoring.py from the dimension findings and the
    journal's risk-weight vector + hard-gate rules — NOT by an LLM.
    """
    venue: str
    rri: int = 0                                  # 0..100 recommendation-risk index
    tier: str = ""                               # 低 / 中 / 偏高 / 高
    predicted_decision: str = ""                 # binary: accept/reject; tiered: +minor/major
    dim_scores: dict[str, float] = field(default_factory=dict)        # dim -> DimScore 0..4
    contributions: dict[str, float] = field(default_factory=dict)     # dim -> w*DimScore
    hard_gate_triggered: list[str] = field(default_factory=list)      # reasons (binary veto)
    decision_model: str = "tiered"               # binary | tiered
    accept_percentile: int | None = None         # this RRI's percentile within the venue's
                                                 # published-accepted RRI distribution (calibration)


@dataclass
class RevisionItem:
    """A priority-ranked, cross-journal-aware fix suggestion."""
    issue: str = ""
    fix_suggestion: str = ""
    dimension: str = ""
    severity: float = 0.0
    fixability: float = 0.5
    priority: float = 0.0                         # Σ_journals severity*w*fixability
    best_for_venues: list[str] = field(default_factory=list)
    conflict_note: str = ""                       # cross-journal tension, if any


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
    risk: RiskScore | None = None
    revision_plan: list[RevisionItem] = field(default_factory=list)
    quality_critique: dict[str, Any] = field(default_factory=dict)
    ai_detection: dict[str, Any] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)          # per-stage provenance


@dataclass
class CrossJournalReport:
    """One paper scored against several journals from a single set of findings."""
    paper_id: str
    venues: list[str] = field(default_factory=list)
    desk_screen: dict[str, Any] = field(default_factory=dict)
    dimension_reviews: list[DimensionReview] = field(default_factory=list)
    verifications: list[VerificationResult] = field(default_factory=list)
    risks: list[RiskScore] = field(default_factory=list)              # one per venue
    meta_reviews: dict[str, MetaReview] = field(default_factory=dict) # venue -> meta
    revision_plan: list[RevisionItem] = field(default_factory=list)   # unified, cross-journal
    recommended_venue: str = ""
    rationale: str = ""
    quality_critique: dict[str, Any] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)
