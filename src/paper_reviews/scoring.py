"""Deterministic risk scoring — ported from review_simulator's risk methodology.

The LLM reviewers emit evidence-grounded *findings* with severity/confidence/
fixability. Turning those into a comparable acceptance-risk index is a pure
arithmetic step, so we do it in Python (not in an LLM) for reproducibility and to
honour the project's design rule "聚合不独裁、分数确定化".

Methodology (review_simulator/01_design/01_风险评分方法论.md):
- DimScore(Dk) = max_i ( severity_i * (0.5 + 0.5*confidence_i) )           ∈ [0,4]
- RawRisk      = Σ_k w_k(journal) * DimScore(Dk)                            ∈ [0,4]
- RRI          = round(RawRisk / 4 * 100)                                   ∈ [0,100]
- binary (IEEE Access): any hard-gate finding with severity≥3 → RRI = max(RRI, 75)
- Priority(fix) = Σ_journals severity * w_dim(journal) * fixability
"""
from __future__ import annotations

from .config import JournalProfile
from .models import (CrossJournalReport, DimensionReview, Finding, RevisionItem,
                     RiskScore)

# risk tier thresholds (RRI -> label)
_TIERS = [(25, "低"), (50, "中"), (70, "偏高"), (100, "高")]
HARD_GATE_FLOOR = 75


def _all_findings(reviews: list[DimensionReview]) -> list[Finding]:
    out: list[Finding] = []
    for r in reviews:
        out.extend(r.findings)
    return out


def dim_score(findings: list[Finding], dim: str) -> float:
    """Confidence-weighted MAX severity for one dimension (the worst single cut)."""
    vals = [f.severity * (0.5 + 0.5 * f.confidence)
            for f in findings if f.dimension == dim]
    return round(max(vals), 3) if vals else 0.0


def risk_tier(rri: int) -> str:
    for ceiling, label in _TIERS:
        if rri <= ceiling:
            return label
    return "高"


def predicted_decision(rri: int, decision_model: str, hard_gated: bool) -> str:
    """Map RRI -> a venue-appropriate predicted decision."""
    if decision_model == "binary":
        # IEEE Access: accept / reject (no major-revision buffer)
        if hard_gated or rri > 50:
            return "reject"
        if rri <= 25:
            return "accept"
        return "borderline-reject"   # 26–50: 边缘，无大修缓冲 → 偏拒
    # tiered (MDPI): accept / minor / major / reject
    if rri <= 25:
        return "accept_or_minor"
    if rri <= 50:
        return "minor_or_major"
    if rri <= 70:
        return "major_revision"
    return "major_to_reject"


def score_journal(journal: JournalProfile, reviews: list[DimensionReview]) -> RiskScore:
    """Compute one journal's RiskScore from the shared findings."""
    findings = _all_findings(reviews)
    weights = journal.risk_weights()
    dim_keys = [d.key for d in journal.enabled_dimensions]

    dims = {k: dim_score(findings, k) for k in dim_keys}
    contributions = {k: round(weights.get(k, 0.0) * dims[k], 4) for k in dim_keys}
    raw = sum(contributions.values())                      # ∈ [0,4]
    rri = round(raw / 4 * 100)

    # binary one-veto hard gates (IEEE Access only)
    triggered: list[str] = []
    if journal.decision_model == "binary" and journal.hard_gates:
        gate_dims = {g.get("dimension") for g in journal.hard_gates}
        for f in findings:
            if f.hard_gate and f.severity >= 3:
                triggered.append(f.issue or f.dimension)
            elif f.dimension in gate_dims and f.severity >= 4:
                # a fatal finding on a gated dimension also vetoes
                triggered.append(f"[{f.dimension}] {f.issue}")
        if triggered:
            rri = max(rri, HARD_GATE_FLOOR)

    # calibration: where does this RRI sit within the venue's published-accepted distribution?
    accept_pct = None
    dist = (journal.accept_rri_stats or {}).get("distribution") or []
    if dist:
        accept_pct = round(100 * sum(1 for x in dist if x <= rri) / len(dist))

    return RiskScore(
        venue=journal.venue,
        rri=rri,
        tier=risk_tier(rri),
        predicted_decision=predicted_decision(rri, journal.decision_model, bool(triggered)),
        dim_scores=dims,
        contributions=contributions,
        hard_gate_triggered=triggered,
        decision_model=journal.decision_model,
        accept_percentile=accept_pct,
    )


def build_revision_plan(reviews: list[DimensionReview],
                        journals: list[JournalProfile]) -> list[RevisionItem]:
    """Priority-rank fixes across journals; flag cross-journal weight conflicts.

    Priority = Σ_journals severity * w_dim(journal) * fixability  — high severity,
    high fixability, and broad cross-journal relevance float to the top
    ("highest-ROI fix first").
    """
    weight_by_venue = {j.venue: j.risk_weights() for j in journals}
    items: list[RevisionItem] = []
    for f in _all_findings(reviews):
        if f.severity < 1:                              # skip strengths / non-issues
            continue
        per_venue = {v: w.get(f.dimension, 0.0) for v, w in weight_by_venue.items()}
        priority = round(sum(f.severity * w * f.fixability for w in per_venue.values()), 4)
        # which venues care most about this dimension
        ranked = sorted(per_venue.items(), key=lambda kv: kv[1], reverse=True)
        best = [v for v, w in ranked if w >= 0.9 * (ranked[0][1] or 1e-9)][:2]
        spread = (max(per_venue.values()) - min(per_venue.values())) if per_venue else 0.0
        conflict = ""
        if spread >= 0.06:
            hi = max(per_venue, key=per_venue.get)
            lo = min(per_venue, key=per_venue.get)
            conflict = f"该维度在 {hi} 远比 {lo} 重要（权重差 {spread:.2f}），按目标刊取舍"
        items.append(RevisionItem(
            issue=f.issue, fix_suggestion=f.fix_suggestion, dimension=f.dimension,
            severity=f.severity, fixability=f.fixability, priority=priority,
            best_for_venues=best, conflict_note=conflict,
        ))
    items.sort(key=lambda it: it.priority, reverse=True)
    return items


def recommend_venue(risks: list[RiskScore]) -> tuple[str, str]:
    """Pick the lowest-risk venue and explain why (journal selection as a lever)."""
    if not risks:
        return "", ""
    best = min(risks, key=lambda r: r.rri)
    others = ", ".join(f"{r.venue}={r.rri}({r.tier})" for r in risks if r.venue != best.venue)
    rationale = (f"按录用风险指数，{best.venue} 最低（RRI={best.rri}，{best.tier}风险，"
                 f"预测：{best.predicted_decision}）；其余：{others}。"
                 "期刊选择本身是最大的风险杠杆——同一篇稿件不同刊的风险结构差异显著。")
    return best.venue, rationale


def score_cross_journal(paper_id: str,
                        reviews: list[DimensionReview],
                        verifications: list,
                        journals: list[JournalProfile]) -> CrossJournalReport:
    """Assemble a CrossJournalReport from one shared set of findings."""
    risks = [score_journal(j, reviews) for j in journals]
    plan = build_revision_plan(reviews, journals)
    rec_venue, rationale = recommend_venue(risks)
    return CrossJournalReport(
        paper_id=paper_id,
        venues=[j.venue for j in journals],
        dimension_reviews=reviews,
        verifications=verifications,
        risks=risks,
        revision_plan=plan,
        recommended_venue=rec_venue,
        rationale=rationale,
    )
