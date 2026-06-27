# 项目状态 — paper_reviews

更新：2026-06-27

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

## 阻塞 / 风险
- ⚠️ 本机到 Cloubic 端点连接超时（curl 直连/代理均 40s timeout，http=000）。代码路由正确，
  待排查网络/服务可用性后做真实 LLM 跑测。news-monitor 用同一套 key，可对比验证。

## 待办（优先级）
1. 排通 Cloubic 实跑，用真实 LLM 对一篇真稿（科东论文）跑 ieee_access 全流程
2. CalibrationAgent 实装（rubric 分→目标刊分布去偏）
3. VerificationAgent 接 RAG 查新 / 代码沙箱执行（新颖性 + 经验性 claim 核验）
4. 评测脚本：与人类一致性 MSE/MAE/Spearman、pairwise 排序准确率、Decision F1
5. (可选) AI 代写检测微服务（Fast-DetectGPT，需本地白盒 logits）
6. 去身份化 AnonymizerAgent 实装；报告导出 PDF（复用 reportlab）

## 关键决策（详见 wiki）
借 AgentReview 当"反面基准"而非复刻；独立维度评审优先、保留分歧、inclusive 聚合、分数校准、强模型挑刺。
