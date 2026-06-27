"""Render a ReviewReport into an author-facing markdown review."""
from __future__ import annotations

from .config import JournalProfile
from .models import ReviewReport


def render_markdown(rep: ReviewReport, journal: JournalProfile | None = None) -> str:
    L: list[str] = []
    L.append(f"# 审稿意见 — {rep.paper_id}")
    L.append(f"> 目标期刊：**{rep.venue}**　| 本意见由多智能体系统生成，供作者投稿前自检与编辑参考，"
             f"最终判断须由人类负责。\n")

    # decision banner
    mr = rep.meta_review
    if mr:
        rec = mr.recommendation.value if mr.recommendation else "—"
        L.append("## 综合结论")
        L.append(f"- **建议**：{rec}")
        if mr.overall_score is not None:
            L.append(f"- **总体评分**：{mr.overall_score}")
        if mr.confidence is not None:
            L.append(f"- **置信度**：{mr.confidence}/5")
        if mr.disagreement is not None:
            L.append(f"- **审稿人分歧度**：{mr.disagreement}")
        if mr.needs_human_review:
            L.append("- ⚠️ **需人工复核**（分歧大或置信度低）")
        if mr.summary:
            L.append(f"\n{mr.summary}\n")

    # venue match
    if rep.venue_match:
        vm = rep.venue_match
        L.append("## 期刊匹配度")
        L.append(f"- 契合度：{vm.get('fit_score','—')}　水平差距：{vm.get('level_gap','—')}")
        L.append(f"- 投稿建议：{vm.get('recommendation','—')}")
        if vm.get("rationale"):
            L.append(f"- {vm['rationale']}")
        L.append("")

    # desk screen red flags
    if rep.desk_screen and rep.desk_screen.get("red_flags"):
        L.append("## 桌面初筛风险")
        for f in rep.desk_screen["red_flags"]:
            L.append(f"- {f}")
        L.append("")

    # per-dimension
    L.append("## 分维度评审")
    for r in rep.dimension_reviews:
        smax = int(r.scale_max) if r.scale_max else "?"
        L.append(f"### {r.dimension}　（评分 {r.score}/{smax}，置信 {r.confidence or '—'}）")
        if r.strengths:
            L.append("**优点**")
            L += [f"- {s}" for s in r.strengths]
        if r.weaknesses:
            L.append("**问题/缺点**")
            L += [f"- {w}" for w in r.weaknesses]
        if r.questions:
            L.append("**给作者的问题**")
            L += [f"- {q}" for q in r.questions]
        L.append("")

    # verification
    if rep.verifications:
        L.append("## 对抗式核验")
        for v in rep.verifications:
            flag = "（改变了原判断）" if v.changed_assessment else ""
            L.append(f"- [{v.target}] **{v.verdict}**{flag}：{v.rationale}")
        L.append("")

    # actionable revisions
    if mr and mr.actionable_revisions:
        L.append("## 修改清单（按优先级）")
        for i, a in enumerate(mr.actionable_revisions, 1):
            L.append(f"{i}. {a}")
        L.append("")

    # quality critique
    if rep.quality_critique:
        qc = rep.quality_critique
        L.append("## 审稿质量自评")
        L.append(f"- specificity={qc.get('specificity','—')} "
                 f"coverage={qc.get('coverage','—')} "
                 f"groundedness={qc.get('groundedness','—')}")
        if qc.get("flagged_items"):
            L.append("- 待改进的意见条目：")
            L += [f"  - {x}" for x in qc["flagged_items"]]
        L.append("")

    return "\n".join(L)
