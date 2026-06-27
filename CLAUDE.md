# CLAUDE.md — paper_reviews 项目上下文

## 项目目标
多智能体论文投稿审稿系统。针对**具体目标期刊要求**调度审稿智能体集群，为作者产出
专业、针对性、水平匹配该刊的详细审稿意见与修改清单。定位：**人类评审的辅助/投稿前自检**，
非替代人类评审。

## 技术栈
- Python 3.11+，httpx 同步客户端，OpenAI 兼容接口
- LLM 路由：Cloubic 统一网关（`.env.cloubic`），claude/gemini/openai/glm/qwen/deepseek 走降级链；
  kimi/doubao/grok 直连。路由代码 `src/paper_reviews/cloubic.py`（移植自 news-monitor）。
- 配置驱动：期刊画像 YAML (`config/journals/`) + 智能体模型映射 (`config/agents.yaml`)

## 关键文件
- `src/paper_reviews/orchestrator.py` — 流水线编排（并行隔离评审→核验→聚合）
- `src/paper_reviews/agents/{base,prompts,roles}.py` — 智能体与提示词
- `src/paper_reviews/{models,config,ingest,report}.py`
- `config/journals/ieee_access.yaml` — 首个落地期刊画像
- `research/00_技术路线总览与系统设计.md` — 全部设计决策与依据（先读这个）
- `scripts/run_review.py` — CLI

## 常用命令
```bash
python scripts/run_review.py <manuscript> --venue ieee_access -v
python -m py_compile src/paper_reviews/*.py src/paper_reviews/agents/*.py   # 编译检查
```

## 设计铁律（来自 AgentReview 等反面实证，勿违反）
1. 维度评审先**独立隔离**再聚合；"讨论/互见"是可选开关，非默认（互见使方差降 27%、传染偏见）。
2. **保留分歧**，不追求一致；高分歧/低置信→标记需人工复核。
3. 聚合**不独裁也不简单多数**（inclusive AC 最稳）。
4. 输入**严格去身份化**（作者/机构/致谢/自引）。
5. 输出**证据化文字为主、分数为辅**；分数需校准去偏（通用 LLM 系统性偏高）。
6. 强模型 + 显式激励"挑毛病"（弱模型会变好好先生）；关键维度多模型投票。
7. 用 **JSON mode 强约束输出**，不要退回纯正则解析。

## 当前状态（2026-06-27）
- ✅ 脚手架 + 核心流水线已跑通（mock 端到端验证：7 维并行评审→核验→meta→报告）
- ✅ 4 份来源分析 + 技术路线总览已落地 `research/`
- ✅ 移植 Cloubic 路由 + 多 provider 客户端
- ⚠️ 实跑待验证：本机到 Cloubic 端点连接超时（直连/代理均 timeout），需排查网络/服务可用性后做真实 LLM 跑测
- ⏳ 待办：分数校准 CalibrationAgent 实装、RAG 新颖性查新与代码执行核验、AI 代写检测微服务、评测脚本(与人类一致性/pairwise/Decision F1)

## 断线恢复
读 `research/00`、本文件、`memory/project_status.md`、`wiki/README.md` 即可恢复上下文。
不要把 `.env` / `.env.cloubic` 提交到 git。
