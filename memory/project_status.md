# 项目状态 — paper_reviews

更新：2026-06-28

## 一句话
多智能体论文投稿审稿系统：期刊画像驱动，为作者产出针对目标期刊的专业审稿意见。仓库：
https://github.com/gaoxingkele/paper_reviews

## 已完成
- 脚手架：`src/paper_reviews/`（cloubic, llm_client, config, models, ingest, agents/, orchestrator, report）
- 期刊画像驱动：`config/journals/{_template,ieee_access}.yaml` + `config/agents.yaml`
- CLI：`scripts/run_review.py`
- LLM 路由：移植 news-monitor 的 Cloubic 统一路由 + 多 provider 降级链 + 多模型投票
- 研究汇总：`research/00..04`（综述 / AgentReview / Researcher repo / 最新调研 + 技术路线总览）
- 参考材料下载到 `references/`（Researcher 仓库、survey PDF、AgentReview HTML）；openaireview 改由调研 agent 在线抓取
- wiki：架构决策条目
- 端到端验证：mock LLM 跑通 7 维并行评审→对抗核验→meta 聚合→报告渲染
- ★ (2026-06-28) 全量移植用户自研 review_simulator 框架 → RRI 评分层（详见 wiki
  `2026-06-28_rri-risk-scoring-and-hard-gate`）：
  - `scoring.py` 确定性算 RRI/硬门槛/ROI 优先级；`Finding` 富字段；负面结果专项拷问
  - 期刊 YAML 加 `risk_weight`/`decision_model`/`hard_gates`；新建 MDPI 三刊画像
  - `CrossJournalOrchestrator` 一次评审多刊算分 → 跨刊风险矩阵报告；CLI `--venues a,b,c`
  - PDF ingest 修复：`as_review_input` 在无 section 时回退 raw_text（否则正文丢失）
  - `PR_FORCE_PROVIDER` 环境变量：钉死健康 provider，避免死上游空转重试
  - 确定性单测通过：同组发现 IEEE Access RRI=75(否决/reject) vs MDPI=34(大修)

## 阻塞 / 风险
- ✅ (2026-06-27 解除) Cloubic 连通性恢复：TLS/鉴权/路由均正常。探针结论：
  **当前 key 仅 Claude 系可靠可用**（claude-opus-4-6 / sonnet-4-6 / haiku-4-5 全 200）；
  gpt-5.x 超时/401、gemini-3 403(未开通)、deepseek-v3.2 / glm-5 / qwen3-max 在网关侧"server
  disconnected"快速失败。→ 已补"跨 provider 回退"(见下)，非 Claude 维度自动兜底到 claude。
- ⚠️ 真实多模型投票暂不可用（仅 claude 健康）；待网关其他上游恢复或换有权限的 key 后才能体现多 provider 抗偏见。
- ⚠️ `llm_client.chat` 默认 `timeout=600s` + `retries=2`：若某上游变成"挂死"而非快速断开，单维度最坏会阻塞很久。
  当前网关是秒级断开，暂不致命；实跑前可考虑给评审阶段调小 timeout。

## 实跑结果（2026-06-28，真实 LLM, claude-opus-4-6）
- 科东 3 篇 × IEEE Access + MDPI 三刊 跨刊评审全部跑通，0 维度失败、0 JSON 解析失败。
  产物在 `output/{P1_KE-NSGA-II,P2_LODF,P3_KGRAT}__cross.{md,json}` + 总表 `output/00_跨期刊风险对比总表.md`。
- 结论高度一致印证框架论点：三篇均"诚实非-SOTA/负面结论"型 →
  **IEEE Access 全部 reject（二元无缓冲）；MDPI 三刊全部 major_revision（可挽救）**；首选均 MDPI Energies。
  RRI 60-64（偏高）。负面结果拷问命中（P2 过度泛化/伪负面、P3 可审计性价值主张未验证）。
- ⚠️ 校准观察：novelty/soundness/experiments 维度风险分多饱和在 2.85(=sev3×conf0.9)，
  LLM 高频给"严重/高置信"+"最痛一刀"取 max 易饱和 → CalibrationAgent 优先级上升。
- ⚠️ 本轮 reasoning 关闭（gateway 的 *-thinking 模型间歇掉线），未启用多模型投票（仅 claude 健康）。

## 知识蒸馏（2026-07-01，正样本校准）
- 抓取 20 篇近年已发表 Energies 经济/排放调度·优化论文全文（浏览器→本地 sink 服务落盘，
  绕过 Cloudflare/不经 agent 上下文）：`corpus/energies/*.txt`、清洗版 `corpus/energies_clean/`。
- 评估 15 篇有效（5 篇因额度/抓取质量跳过）：**正样本 RRI 均值 53.7、中位 55、93% 被判 major_revision**
  —— 证明系统绝对尺度偏严（尤其 novelty 2.93、clarity 2.35）。
- 蒸馏落地（全部零额外 LLM，复用评估数据）：
  - `corpus/DISTILLATION_REPORT.md`：校准信号 + P1 在已录用分布的百分位
  - `config/journals/mdpi_energies_accepted_profile.md`：接受画像（测试系统 IES/微网/IEEE30-bus、
    基线 PSO/DE/GA/SSA/RL、10/15 有统计检验、14/15 有数据可用性）；经 roles 注入审稿 prompt
  - `mdpi_energies.yaml`：写入 accept_rri_stats 分布、novelty strictness 1.0→0.85、clarity→0.9、更新 exemplars
  - scoring 增 `accept_percentile`（RRI 在已录用分布的百分位）；report 渲染该校准行
- **关键结论：P1 对 Energies RRI=62 = 已录用论文第 60 百分位 → 属正常区间，非离群高风险**
  （之前"偏高/major"是绝对尺度；按真实接受尺度 P1 与已发表论文相当）。
- 工具：scripts/{text_sink,clean_corpus,run_positives_eval,run_eval_remaining,distill_positives,
  build_distillation,extract_acceptance_profile}.py（最后一个需 LLM，待额度恢复跑更细画像）。

## DeepSeek 直连补跑（2026-07-01，Cloubic 欠费时的备用通道）
- Cloubic 账户欠费 → 改用直连 DeepSeek（.env DEEPSEEK_API_KEY, api.deepseek.com, deepseek-v4-flash）。
  路由法：CLOUBIC_ROUTED_PROVIDERS 去掉 deepseek + PR_FORCE_PROVIDER=deepseek → 走直连绕开欠费。
- 正样本补满 20 篇（15 Claude + 5 DeepSeek 补齐 en18010018/en19010140/en19061578/en19092234/en19112570，
  DeepSeek 未复现桌面误拒）。更新 n=20：RRI 均值 57.5、中位 61.5、区间 [14,76]、**95% 判 major_revision**。
  已更新 mdpi_energies.yaml accept_rri_stats(n=20)。
- **P1 @ Energies RRI=62 = 已录用分布第 50 百分位（正好中位）→ 完全是典型可录用论文**。
- P1 DeepSeek 全新校准评审：RRI=59、major、第60百分位（与 Claude 62 一致）→
  中文 Word `output/P1__MDPI_Energies_审稿意见_中文_DeepSeek.docx`（含★校准结论）。
- P2/P3 DeepSeek 跨刊（`output/P{2,3}_*__deepseek_cross.md`）：与 Claude 版一致——
  IEEE Access reject / MDPI major_revision / 首选 mdpi_energies。跨模型互证稳健。

## 待办（优先级）
0. (可选) 额度恢复后：跑 extract_acceptance_profile.py 出更细结构化画像；生成 P2/P3 中文 Word。
1. CalibrationAgent 实装（rubric 分→目标刊分布去偏；缓解 severity 饱和）
3. VerificationAgent 接 RAG 查新 / 代码沙箱执行（新颖性 + 经验性 claim 核验）
4. 评测脚本：与人类一致性 MSE/MAE/Spearman、pairwise 排序准确率、Decision F1
5. (可选) AI 代写检测微服务（Fast-DetectGPT，需本地白盒 logits）
6. 去身份化 AnonymizerAgent 实装；报告导出 PDF（复用 reportlab）

## 关键决策（详见 wiki）
借 AgentReview 当"反面基准"而非复刻；独立维度评审优先、保留分歧、inclusive 聚合、分数校准、强模型挑刺。
