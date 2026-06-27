"""Concrete review agents. Each is a small policy over Agent.run + a prompt."""
from __future__ import annotations

import statistics

from . import prompts as P
from .base import Agent, AgentSpec
from ..config import JournalProfile, RubricDimension
from ..models import (DimensionReview, MetaReview, Recommendation,
                      VerificationResult, Paper)


class DimensionReviewer(Agent):
    """Reviews ONE rubric dimension, independently and evidence-grounded."""

    def review(self, paper: Paper, journal: JournalProfile,
               dim: RubricDimension) -> DimensionReview:
        sys = P.REVIEWER_SYSTEM.format(
            venue_full=journal.full_name or journal.venue,
            aims_scope=journal.aims_scope, level=journal.level,
            dim_label=dim.label,
        )
        user = P.REVIEWER_USER.format(
            dim_label=dim.label, dim_description=dim.description,
            dim_key=dim.key, scale_max=int(dim.scale_max),
            strictness=dim.strictness,
            exemplar_block=P.exemplar_block(journal.exemplars),
            paper=paper.as_review_input(),
        )

        if self.spec.voters > 1 or self.spec.extra_providers:
            ballots = self.run_voting(sys, user)
            return self._aggregate_ballots(dim, ballots)

        data, res = self.run(sys, user)
        return self._to_review(dim, data, res.model)

    def _to_review(self, dim, data, model) -> DimensionReview:
        return DimensionReview(
            dimension=dim.key,
            score=_num(data.get("score")),
            scale_max=dim.scale_max,
            confidence=_num(data.get("confidence")),
            strengths=_listify(data.get("strengths")),
            weaknesses=_listify(data.get("weaknesses")),
            questions=_listify(data.get("questions")),
            evidence=_listify(data.get("evidence")),
            raw=str(data.get("_raw", "")),
            agent=self.name, model=model,
        )

    def _aggregate_ballots(self, dim, ballots) -> DimensionReview:
        """Multi-model voting: average score, union of evidence-bearing points."""
        if not ballots:
            return DimensionReview(dimension=dim.key, scale_max=dim.scale_max,
                                   agent=self.name)
        scores = [_num(b[0].get("score")) for b in ballots if _num(b[0].get("score")) is not None]
        agg = self._to_review(dim, ballots[0][0], ballots[0][1].model)
        agg.score = round(statistics.mean(scores), 2) if scores else None
        # union weaknesses (the parts models disagree on are the most informative)
        for data, _ in ballots[1:]:
            agg.weaknesses += _listify(data.get("weaknesses"))
            agg.strengths += _listify(data.get("strengths"))
        agg.weaknesses = _dedup(agg.weaknesses)
        agg.strengths = _dedup(agg.strengths)
        return agg


class DeskScreener(Agent):
    def screen(self, paper: Paper, journal: JournalProfile) -> dict:
        sys = P.DESK_SCREEN_SYSTEM.format(venue_full=journal.full_name or journal.venue)
        user = P.DESK_SCREEN_USER.format(
            aims_scope=journal.aims_scope, policies=journal.policies,
            paper=paper.as_review_input(max_chars=20_000))
        data, _ = self.run(sys, user)
        return data


class VenueMatcher(Agent):
    def match(self, paper: Paper, journal: JournalProfile) -> dict:
        sys = P.VENUE_MATCH_SYSTEM
        user = P.VENUE_MATCH_USER.format(
            venue_full=journal.full_name or journal.venue, level=journal.level,
            aims_scope=journal.aims_scope, decision_threshold=journal.decision_threshold,
            paper=paper.as_review_input(max_chars=20_000))
        data, _ = self.run(sys, user)
        return data


class Verifier(Agent):
    def verify(self, dimension: str, claim: str, context: str) -> VerificationResult:
        sys = P.VERIFY_SYSTEM
        user = P.VERIFY_USER.format(dimension=dimension, claim=claim, context=context)
        data, _ = self.run(sys, user)
        return VerificationResult(
            target=data.get("target", dimension),
            verdict=data.get("verdict", "uncertain"),
            rationale=data.get("rationale", ""),
            sources=_listify(data.get("sources")),
            changed_assessment=bool(data.get("changed_assessment", False)),
        )


class MetaReviewer(Agent):
    def aggregate(self, journal: JournalProfile,
                  reviews: list[DimensionReview],
                  verifications: list[VerificationResult]) -> MetaReview:
        import json
        sys = P.META_SYSTEM.format(venue_full=journal.full_name or journal.venue)
        rv = json.dumps([_review_dict(r) for r in reviews], ensure_ascii=False, indent=1)
        vf = json.dumps([v.__dict__ for v in verifications], ensure_ascii=False, indent=1)
        user = P.META_USER.format(
            decision_threshold=journal.decision_threshold,
            score_distribution=journal.score_distribution,
            dimension_reviews=rv, verifications=vf)
        data, _ = self.run(sys, user)

        rec = data.get("recommendation")
        try:
            rec_enum = Recommendation(rec) if rec else None
        except ValueError:
            rec_enum = None
        return MetaReview(
            summary=data.get("summary", ""),
            recommendation=rec_enum,
            overall_score=_num(data.get("overall_score")),
            confidence=_num(data.get("confidence")),
            disagreement=_num(data.get("disagreement")),
            needs_human_review=bool(data.get("needs_human_review", False)),
            key_strengths=_listify(data.get("key_strengths")),
            key_concerns=_listify(data.get("key_concerns")),
            actionable_revisions=_listify(data.get("actionable_revisions")),
        )


class ReviewCritic(Agent):
    def critique(self, abstract: str, review_json: str) -> dict:
        sys = P.CRITIC_SYSTEM
        user = P.CRITIC_USER.format(abstract=abstract[:4000], review=review_json[:20000])
        data, _ = self.run(sys, user)
        return data


# ---- helpers ----
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _listify(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    return [str(v)]


def _dedup(items):
    seen, out = set(), []
    for x in items:
        k = x.strip().lower()[:80]
        if k and k not in seen:
            seen.add(k)
            out.append(x)
    return out


def _review_dict(r: DimensionReview) -> dict:
    return {"dimension": r.dimension, "score": r.score, "scale_max": r.scale_max,
            "confidence": r.confidence, "strengths": r.strengths,
            "weaknesses": r.weaknesses, "questions": r.questions}
