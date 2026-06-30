"""Concrete review agents. Each is a small policy over Agent.run + a prompt."""
from __future__ import annotations

import statistics

from . import prompts as P
from .base import Agent, AgentSpec
from ..config import JournalProfile, RubricDimension
from ..models import (DimensionReview, Finding, MetaReview, Recommendation,
                      RiskScore, VerificationResult, Paper)


def targets_block(journals: list[JournalProfile]) -> str:
    """Describe the target journal(s) so reviewers can set journal_sensitivity."""
    lines = []
    for j in journals:
        lines.append(f"- 《{j.full_name or j.venue}》 (venue={j.venue}, "
                     f"decision_model={j.decision_model})：{j.aims_scope.strip()[:160]}")
    return "\n".join(lines)


class DimensionReviewer(Agent):
    """Reviews ONE rubric dimension, independently and evidence-grounded."""

    def review(self, paper: Paper, journal: JournalProfile,
               dim: RubricDimension,
               targets: list[JournalProfile] | None = None) -> DimensionReview:
        targets = targets or [journal]
        sys = P.REVIEWER_SYSTEM.format(
            venue_full=journal.full_name or journal.venue,
            aims_scope=journal.aims_scope, level=journal.level,
            dim_label=dim.label,
        )
        exemplar_block = P.exemplar_block(journal.exemplars)
        # inject the distilled "what this venue actually accepts" profile so the
        # reviewer calibrates to real accepted papers, not a generic harsh bar
        profile = journal.acceptance_profile_text()
        if profile:
            exemplar_block += ("\n## 该刊真实接受画像（从已发表正样本蒸馏，用于校准严格度，勿照搬为优点）\n"
                               + profile + "\n")
        user = P.REVIEWER_USER.format(
            dim_label=dim.label, dim_description=dim.description,
            dim_key=dim.key, scale_max=int(dim.scale_max),
            strictness=dim.strictness,
            venue_full=journal.full_name or journal.venue,
            targets_block=targets_block(targets),
            exemplar_block=exemplar_block,
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
            findings=_parse_findings(dim.key, data.get("findings")),
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
        # union weaknesses/findings (the parts models disagree on are the most informative)
        for data, _ in ballots[1:]:
            agg.weaknesses += _listify(data.get("weaknesses"))
            agg.strengths += _listify(data.get("strengths"))
            agg.findings += _parse_findings(dim.key, data.get("findings"))
        agg.weaknesses = _dedup(agg.weaknesses)
        agg.strengths = _dedup(agg.strengths)
        agg.findings = _dedup_findings(agg.findings)
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
                  verifications: list[VerificationResult],
                  risk: RiskScore | None = None) -> MetaReview:
        import json
        sys = P.META_SYSTEM.format(venue_full=journal.full_name or journal.venue)
        rv = json.dumps([_review_dict(r) for r in reviews], ensure_ascii=False, indent=1)
        vf = json.dumps([v.__dict__ for v in verifications], ensure_ascii=False, indent=1)
        user = P.META_USER.format(
            decision_threshold=journal.decision_threshold,
            score_distribution=journal.score_distribution,
            decision_model=journal.decision_model,
            risk_block=_risk_block(risk),
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


def _clamp(v, lo, hi, default):
    n = _num(v)
    if n is None:
        return default
    return max(lo, min(hi, n))


def _parse_findings(dim_key: str, raw) -> list[Finding]:
    if not isinstance(raw, list):
        return []
    out: list[Finding] = []
    for f in raw:
        if not isinstance(f, dict):
            continue
        out.append(Finding(
            dimension=dim_key,
            severity=_clamp(f.get("severity"), 0, 4, 0.0),
            confidence=_clamp(f.get("confidence"), 0, 1, 0.5),
            fixability=_clamp(f.get("fixability"), 0, 1, 0.5),
            issue=str(f.get("issue", "")).strip(),
            reviewer_voice=str(f.get("reviewer_voice", "")).strip(),
            evidence=str(f.get("evidence", "")).strip(),
            journal_sensitivity=str(f.get("journal_sensitivity", "")).strip(),
            hard_gate=bool(f.get("hard_gate", False)),
            fix_suggestion=str(f.get("fix_suggestion", "")).strip(),
        ))
    return out


def _dedup_findings(items: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in items:
        k = (f.dimension, (f.issue or "").strip().lower()[:80])
        if k[1] and k not in seen:
            seen.add(k)
            out.append(f)
    return out


def _risk_block(risk: RiskScore | None) -> str:
    if not risk:
        return "（未提供，自行判断）"
    parts = [f"RRI={risk.rri}/100（{risk.tier}风险），预测决策={risk.predicted_decision}"]
    if risk.hard_gate_triggered:
        parts.append("⚠ 触发 IEEE Access 一票否决：" + "；".join(risk.hard_gate_triggered[:3]))
    ds = ", ".join(f"{k}:{v}" for k, v in risk.dim_scores.items())
    parts.append(f"各维度风险分(0-4): {ds}")
    return "\n".join(parts)


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
