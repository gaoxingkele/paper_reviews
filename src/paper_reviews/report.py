"""Render a ReviewReport into an author-facing markdown review."""
from __future__ import annotations

from .config import JournalProfile, load_journal
from .models import CrossJournalReport, ReviewReport, RiskScore


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

    # deterministic risk index
    if rep.risk:
        L.append(_risk_section(rep.risk))

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
        if r.findings:
            L.append("**审稿人原话级发现（severity/可修复性）**")
            for f in sorted(r.findings, key=lambda x: x.severity, reverse=True):
                gate = " 🚫一票否决" if f.hard_gate else ""
                L.append(f"- [sev {int(f.severity)}/4 · fix {f.fixability:.1f}{gate}] "
                         f"**{f.issue}**")
                if f.reviewer_voice:
                    L.append(f"  > {f.reviewer_voice}")
                if f.evidence:
                    L.append(f"  · 证据：{f.evidence}")
                if f.journal_sensitivity:
                    L.append(f"  · 期刊敏感度：{f.journal_sensitivity}")
                if f.fix_suggestion:
                    L.append(f"  · 建议：{f.fix_suggestion}")
        L.append("")

    # verification
    if rep.verifications:
        L.append("## 对抗式核验")
        for v in rep.verifications:
            flag = "（改变了原判断）" if v.changed_assessment else ""
            L.append(f"- [{v.target}] **{v.verdict}**{flag}：{v.rationale}")
        L.append("")

    # actionable revisions — prefer the deterministic priority-ranked plan
    if rep.revision_plan:
        L.append("## 修改清单（按 ROI 优先级：severity×权重×可修复性）")
        for i, it in enumerate(rep.revision_plan[:15], 1):
            L.append(f"{i}. **[{it.dimension} · P={it.priority:.2f}]** {it.issue}")
            if it.fix_suggestion:
                L.append(f"   - 建议：{it.fix_suggestion}")
            if it.conflict_note:
                L.append(f"   - ⚖ {it.conflict_note}")
        L.append("")
    elif mr and mr.actionable_revisions:
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


def _risk_section(risk: RiskScore) -> str:
    L = ["## 录用风险指数 (RRI)"]
    L.append(f"- **RRI = {risk.rri}/100　风险档：{risk.tier}　预测决策：{risk.predicted_decision}**"
             f"（决策模型：{risk.decision_model}）")
    if risk.accept_percentile is not None:
        L.append(f"- 校准：该 RRI 处于本刊【已发表论文】风险分布的第 **{risk.accept_percentile}** 百分位"
                 f"（≤50 表示与多数已录用论文相当甚至更稳）")
    if risk.hard_gate_triggered:
        L.append("- 🚫 **触发 IEEE Access 一票否决**：")
        L += [f"  - {t}" for t in risk.hard_gate_triggered]
    if risk.dim_scores:
        cells = "　".join(f"{k}={v:.2f}" for k, v in risk.dim_scores.items())
        L.append(f"- 各维度风险分(0–4)：{cells}")
    L.append("")
    return "\n".join(L)


def render_cross_journal_markdown(cj: CrossJournalReport) -> str:
    """Render the journal×dimension risk matrix + cross-journal submission advice."""
    journals = [load_journal(v) for v in cj.venues]
    dim_keys = [d.key for d in journals[0].enabled_dimensions]
    L: list[str] = []
    L.append(f"# 跨期刊审稿风险报告 — {cj.paper_id}")
    L.append("> 多智能体系统生成：一次维度评审 → 各刊权重向量确定性计算录用风险。"
             "供作者投稿前自检与**期刊选择**参考，最终判断须由人类负责。\n")

    # recommendation
    if cj.recommended_venue:
        L.append("## 投稿建议（期刊选择是最大的风险杠杆）")
        L.append(f"- **首选期刊：{cj.recommended_venue}**")
        L.append(f"- {cj.rationale}\n")

    # risk summary table
    L.append("## 各刊录用风险一览")
    L.append("| 期刊 | RRI | 风险档 | 预测决策 | 一票否决 |")
    L.append("|---|---|---|---|---|")
    for r in cj.risks:
        gate = "；".join(r.hard_gate_triggered)[:60] if r.hard_gate_triggered else "—"
        L.append(f"| {r.venue} | **{r.rri}** | {r.tier} | {r.predicted_decision} | {gate} |")
    L.append("")

    # journal × dimension contribution matrix
    L.append("## 风险矩阵（期刊 × 维度，单元格=加权贡献值）")
    header = "| 期刊 \\\\ 维度 | " + " | ".join(dim_keys) + " | RRI |"
    L.append(header)
    L.append("|" + "---|" * (len(dim_keys) + 2))
    for r in cj.risks:
        row = [r.venue]
        for k in dim_keys:
            row.append(f"{r.contributions.get(k, 0):.3f}")
        row.append(f"**{r.rri}**")
        L.append("| " + " | ".join(row) + " |")
    L.append("")
    # transposed view: which dimension is the raw risk driver (journal-agnostic DimScore)
    L.append("各维度原始风险分(0–4，跨刊共用)：")
    if cj.risks:
        ds = cj.risks[0].dim_scores
        L.append("　".join(f"`{k}={ds.get(k,0):.2f}`" for k in dim_keys))
    L.append("")

    # unified priority-ranked revision plan
    if cj.revision_plan:
        L.append("## 统一修改清单（按 ROI 优先级，跨刊通用）")
        for i, it in enumerate(cj.revision_plan[:18], 1):
            venues = ("，利于：" + "/".join(it.best_for_venues)) if it.best_for_venues else ""
            L.append(f"{i}. **[{it.dimension} · P={it.priority:.2f}]** {it.issue}{venues}")
            if it.fix_suggestion:
                L.append(f"   - 建议：{it.fix_suggestion}")
            if it.conflict_note:
                L.append(f"   - ⚖ 跨刊冲突：{it.conflict_note}")
        L.append("")

    # per-journal meta verdict
    L.append("## 各刊主编（Area Chair）裁决")
    for v, mr in cj.meta_reviews.items():
        rec = mr.recommendation.value if mr.recommendation else "—"
        flag = " ⚠️需人工复核" if mr.needs_human_review else ""
        L.append(f"### {v} → **{rec}**（score {mr.overall_score}/10，置信 {mr.confidence}/5）{flag}")
        if mr.summary:
            L.append(mr.summary)
        if mr.key_concerns:
            L.append("**主要顾虑**")
            L += [f"- {c}" for c in mr.key_concerns]
        L.append("")

    # shared per-dimension detail (findings with reviewer_voice)
    L.append("## 分维度评审（跨刊共用发现）")
    for r in cj.dimension_reviews:
        smax = int(r.scale_max) if r.scale_max else "?"
        L.append(f"### {r.dimension}（主刊评分 {r.score}/{smax}）")
        if r.strengths:
            L.append("**优点**")
            L += [f"- {s}" for s in r.strengths]
        if r.findings:
            L.append("**问题（severity/可修复性 + 原话级评语）**")
            for f in sorted(r.findings, key=lambda x: x.severity, reverse=True):
                gate = " 🚫" if f.hard_gate else ""
                L.append(f"- [sev {int(f.severity)}/4 · fix {f.fixability:.1f}{gate}] **{f.issue}**")
                if f.reviewer_voice:
                    L.append(f"  > {f.reviewer_voice}")
                if f.evidence:
                    L.append(f"  · 证据：{f.evidence}")
                if f.journal_sensitivity:
                    L.append(f"  · 期刊敏感度：{f.journal_sensitivity}")
                if f.fix_suggestion:
                    L.append(f"  · 建议：{f.fix_suggestion}")
        L.append("")

    if cj.verifications:
        L.append("## 对抗式核验")
        for vr in cj.verifications:
            flag = "（改变了原判断）" if vr.changed_assessment else ""
            L.append(f"- [{vr.target}] **{vr.verdict}**{flag}：{vr.rationale}")
        L.append("")

    return "\n".join(L)
