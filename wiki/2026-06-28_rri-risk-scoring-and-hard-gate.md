# 录用风险指数 (RRI) + 二元一票否决 + 跨刊风险矩阵

- **日期**：2026-06-28
- **出处**：用户自研框架 **review_simulator**（"多 Agent 论文评审模拟器"），随项目交付于
  `references/review_simulator.zip`（解压在 `references/review_simulator_extracted/`）。
  其事实地基为官方一手审稿标准：
  - IEEE Access Reviewer Guidelines / Preparing Your Article / Submission Guidelines / Stages of Peer Review
    （https://ieeeaccess.ieee.org/reviewers/reviewer-guidelines/ 等）
  - MDPI Reviewer Brochure（https://mdpi-res.com/data/mdpi-reviewer-brochure-2022.pdf）+ Review Report Form
    + DORA 立场（https://sfdora.org/）
- **谱系**：在 [[2026-06-27_multi-agent-review-architecture]]（期刊画像驱动 + 独立维度评审 + 对抗核验 +
  inclusive 聚合）之上**叠加评分/输出层**，不取代其架构。

## 解决什么根本问题
原架构能产出"证据化的分维度意见 + inclusive meta 裁决"，但对**作者的投稿决策**仍不够直接：
1. 只有一个连续 `decision_threshold=6.0` 软阈值，**误表达了 IEEE Access 的二元 accept/reject 模型**
   （IEEE Access 没有大修缓冲、且有官方红线"语法硬伤即拒"）。
2. 没有**跨刊可比**的风险量化——作者最需要的决策其实是"投哪本刊风险最低"，而期刊选择本身是最大杠杆。
3. 改进建议没有**ROI 排序**：哪条修改"便宜又高影响"、哪条"要重做实验"，没有区分。
4. 对"诚实的非-SOTA / 负面结论"型论文（科东这 3 篇全是）缺专项拷问——这类论文风险从"创新性"
   转移到"价值叙事是否撑得起非-SOTA 定位"和"负面结果是否伪负面"。

## 这个思想的核心直觉
把定性发现压成一个**可比较的标量**，再用**期刊权重向量**让同一组发现在不同刊得到不同风险：
- 每条发现给 `severity(0–4) × confidence(0–1) × fixability(0–1)`。
- 维度分取"**最痛的一刀**"而非平均：`DimScore = max_i severity_i×(0.5+0.5·conf_i)`。
  （平均会稀释致命缺陷；审稿决策由最严重问题主导。）
- `RRI = Σ_k w_k(journal)·DimScore_k / 4 × 100`。IEEE Access 把 技术/实验/复现 权重压到 ~0.60；
  MDPI 把 创新/价值(Interest/Merit) 抬高。**同一组发现 → 不同刊不同 RRI**，这就是风险矩阵。
- **二元刊一票否决**：IEEE Access 任一 `hard_gate` 发现且 severity≥3 → RRI 直接 ≥75（拒）。MDPI 不否决，导大修。
- 改进 ROI：`Priority = Σ_journals severity·w_dim·fixability` —— 便宜、高影响、多刊共同关注的修改排最前。

直觉验证（确定性单测，2026-06-28）：构造一条 soundness 致命 hard_gate 发现 + 中等问题，
IEEE Access → RRI=75/高/reject（否决触发）；MDPI Energies 同样发现 → RRI=34/中/minor_or_major。
**期刊哲学差异被量化复现**，正是该框架的核心价值。

## 我们怎么改造/取舍它
**采用**（移植进本系统的独立隔离流水线）：
- 评分方法论全套 → `src/paper_reviews/scoring.py`（**确定性 Python 计算，不让 LLM 算分**，符合设计铁律
  "聚合不独裁、分数确定化、JSON 强约束"）。
- `Finding` 富字段（severity/confidence/fixability/reviewer_voice/evidence/journal_sensitivity/hard_gate/
  fix_suggestion）→ `models.py` + reviewer prompt。
- 负面结果 / 消融反转专项拷问 → 写进 `REVIEWER_SYSTEM`。
- 期刊权重向量 + 决策模型 + 硬门槛 → 期刊 YAML（`risk_weight`/`decision_model`/`hard_gates`）；
  新建 MDPI 三刊画像。
- 跨刊一次评审、N 刊算分 → `CrossJournalOrchestrator`（方法论 §7：findings 跨刊共用，按各刊权重算 RRI，
  比"每刊重审一遍"省 ~4×）。

**改造 / 取舍**：
- 维度仍用本系统的 **7 个内容维度独立隔离**（AgentReview 实证铁律），而非该框架"3 角色 Agent"分组
  （组内有少量串扰）；把该框架 D1–D7 映射到 7 内容维度，权重向量按映射重算。
- "价值/读者兴趣(Interest/Merit)"折进 `clarity` 维度（MDPI 下其 `risk_weight` 抬高），不新增维度以保证
  跨刊矩阵维度一致。
- 严格排除排版/字体/图片格式（遵循用户 `审稿要求.md`：内容向审稿）。

## 证据 / 反例
- 支持：AgentReview（arXiv:2406.12708）证明"独立隔离 > 互见讨论"（互见使方差降但传染偏见）——故保留本系统
  隔离架构而非采纳该框架的角色分组讨论。RRI/硬门槛/ROI 是该框架对**作者决策面**的增量，与隔离架构正交。
- 反例/局限：RRI 权重向量是**专家先验**而非拟合值，跨刊绝对可比性有限（适合相对排序，不宜当录用概率）；
  hard_gate 由 LLM 判定，需人工复核（已在 meta 触发 needs_human_review）。

## 移植提示
搬到别的期刊体系（NSFC/其他刊）：
1. 复制一个期刊 YAML，改 `decision_model`（binary/tiered）、`risk_weight` 向量（Σ≈1）、`hard_gates` 规则。
2. `scoring.py` 与 prompt 无需改（维度键一致即可）；跨刊只要把多个 venue 传给 `CrossJournalOrchestrator`。
3. 坑：① `as_review_input` 对 PDF 要回退 `raw_text`（PDF 无 section 标记，否则正文丢失，已修）；
   ② 网关只有部分模型可用时用 `PR_FORCE_PROVIDER=claude` 钉死健康 provider，避免在死 provider 上空转重试；
   ③ 去身份化 Agent 尚未实装，PDF 作者身份会进 prompt（投稿前自检场景可接受，正式盲审需先脱敏）。
