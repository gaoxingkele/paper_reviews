# paper_reviews — 多智能体论文投稿审稿系统

面向**作者投稿前自检 / 编辑预筛**的多智能体审稿系统：针对**具体目标期刊的要求**，调度一组
专业审稿智能体（集群），产出**专业、针对性、水平匹配该刊要求**的详细审稿意见与修改清单。

> 定位红线：当前阶段 AI 审稿是**人类评审的辅助**，最终结论由人类负责。系统强在技术细节核查、
> 可复现性、覆盖度；新颖性与学术品味仍以人类判断为准。详见 `research/00_技术路线总览与系统设计.md`。

## 核心特性

- **期刊画像驱动**：每个期刊一份 `config/journals/<venue>.yaml`（aims&scope + rubric + 评分量表 +
  分布 + persona + 红线 + 锚点样例）。换期刊只改 YAML，代码不动 → 实现"针对性 / 水平匹配"。
- **多维度独立评审**：novelty / soundness / experiments / reproducibility / related_work /
  clarity / ethics 各由专门 agent **并行、隔离**评审（规避从众与偏见传染）。
- **对抗式核验**：Verifier 以"反驳"视角核查最严重的缺点，可推翻乐观结论（抗幻觉）。
- **inclusive 聚合**：Meta-Reviewer 兼听但不独裁，**保留分歧**，高分歧/低置信自动标记"需人工复核"。
- **审稿质量自评**：specificity / coverage / groundedness 过滤笼统、无依据、跑题的意见。
- **多模型路由 + 投票**：复用 Cloubic 统一路由（claude/gemini/openai/glm/qwen/deepseek 降级链），
  关键维度跨 provider 多模型投票。

## 流水线

```
解析 → 去身份化 → 桌面初筛 + 期刊匹配 → 多维度独立评审 → 对抗核验
     → 分数校准 → 元评审/决策(保留分歧) → (可选)作者答辩 → 审稿质量自评 → 出报告
```

## 快速开始

```bash
pip install -r requirements.txt
# .env / .env.cloubic 已含 LLM key 与 Cloubic 路由（勿提交）

python scripts/run_review.py path/to/manuscript.md --venue ieee_access -v
# 产出 output/<id>__ieee_access.md 与 .json
```

代码用法：

```python
from paper_reviews.ingest import load_paper
from paper_reviews.orchestrator import review_paper
from paper_reviews.report import render_markdown
from paper_reviews.config import load_journal

paper = load_paper("manuscript.md")
rep = review_paper("ieee_access", paper)
print(render_markdown(rep, load_journal("ieee_access")))
```

## 目录结构

```
config/
  agents.yaml              # 智能体→模型映射（provider/reasoning/投票）
  journals/               # 期刊画像（_template.yaml + ieee_access.yaml）
src/paper_reviews/
  cloubic.py              # Cloubic 统一路由（移植自 news-monitor）
  llm_client.py           # 多 provider OpenAI 兼容客户端 + 降级链
  config.py               # 加载期刊画像 / agent 配置
  models.py               # Paper / DimensionReview / MetaReview / ReviewReport
  ingest.py               # 稿件解析（LaTeX>MD>TXT>PDF）
  agents/                 # base / prompts / roles（各审稿 agent）
  orchestrator.py         # 按期刊画像编排流水线（并行+隔离+聚合）
  report.py               # 渲染作者向 markdown 审稿意见
scripts/run_review.py     # CLI
research/                 # 4 份来源分析 + 技术路线总览（设计依据）
references/               # 下载的论文与仓库（学习材料，git 忽略）
wiki/                     # 思维演化 wiki（为什么这样设计）
memory/                   # 项目状态
```

## 新增一个期刊

1. 复制 `config/journals/_template.yaml` → `config/journals/<venue>.yaml`
2. 填 aims&scope、rubric 维度与权重/严格度、录用线与分布、红线、锚点样例
3. （可选）在 `config/agents.yaml` 为该刊重点维度调强模型 / 多模型投票
4. `python scripts/run_review.py paper.md --venue <venue>`

## 设计依据（研究来源）

- 综述 *LLMs for Automated Scholarly Paper Review* (arXiv:2501.10326)
- *AgentReview* (arXiv:2406.12708, EMNLP'24) — 审稿偏见的反面基准
- zhu-minjun/Researcher — DeepReviewer / CycleReviewer
- OpenAIReview / OpenReviewer / MARG / MAMORX / FactReview / ReViewGraph / DeepReview 等
- 详见 `research/` 与 `wiki/`
