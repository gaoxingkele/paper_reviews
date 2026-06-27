# 期刊画像驱动的多智能体审稿架构

- **日期**：2026-06-27
- **出处**：
  - 综述 *Large Language Models for Automated Scholarly Paper Review: A Survey*, arXiv:2501.10326
  - *AgentReview: Exploring Peer Review Dynamics with LLM Agents*, Jin et al., EMNLP 2024, arXiv:2406.12708, https://github.com/Ahren09/AgentReview
  - *DeepReview* / CycleReviewer, zhu-minjun/Researcher, arXiv:2503.08569 / arXiv:2411.00816, https://github.com/zhu-minjun/Researcher
  - *MARG* arXiv:2401.04259；*MAMORX* (NeurIPS'24)；*FactReview* arXiv:2604.04074；*OpenReviewer* arXiv:2412.11948；*ReViewGraph* arXiv:2511.08317
- **谱系**：取代了"单 LLM 一次性打分"与"AgentReview 式全仿真讨论"两条朴素路线（理由见下）

## 解决什么根本问题
作者要在投稿前知道"这篇按**目标期刊**的标准能不能过、差在哪、怎么改"。
两条朴素路线都不够：
1. **单 LLM 直接打分**：系统性给分偏高（GPT-4o 6.9–8.1 vs 人类 ~5.4，arXiv:2412.11948），
   意见笼统、易幻觉、对期刊差异无感。
2. **全仿真同行评审（AgentReview 式 reviewer↔author↔AC 多轮讨论）**：AgentReview 的价值恰恰是
   **暴露偏见**——互见使评分标准差降 27.2%、偏见传染、rebuttal 几乎不改决策（锚定首因）。
   照搬"讨论"等于把人类评审的缺陷也复制进来。

## 这个思想的核心直觉
把"可靠的针对性审稿"拆成三个正交支柱：
1. **期刊画像 = 一等输入**（综述指出的最大空白）。aims&scope + rubric + 评分量表 + 分数分布 +
   红线 + 锚点样例写进 YAML，注入每个 agent 的 prompt。换刊=换 YAML → 天然实现"针对性/水平匹配"。
2. **独立维度评审 + 对抗核验**（借 MAMORX 按维度分 agent、FactReview 执行核验、MARG 分片分工）。
   每个维度一个专家 agent，**并行且互不可见**（避开 AgentReview 的从众陷阱）；再用一个"反驳视角"
   的 Verifier 去核最严重的缺点，可推翻乐观结论（FactReview 实测执行代码改变 17% 的 claim 判定）。
3. **inclusive 聚合 + 保留分歧**（AgentReview 实证 inclusive AC 最稳，独裁 κ=0.27）。
   Meta-Reviewer 兼听但保留独立判断；**显式上报评审间方差**，高分歧/低置信→标记需人工复核，
   而不是粉饰成虚假共识。

一句话：**借 AgentReview 当"反面基准"（要主动对抗的偏见清单），而非要复刻的系统。**

## 我们怎么改造/取舍它
- 采用综述的 8 阶段管线为骨架，但把 AgentReview 的"讨论/rebuttal"设为**默认关闭的可选开关**。
- 采用 DeepReviewer 的"模拟多 reviewer + self-verification + 三档深度"思路，但**拆成 N 个并行
  httpx agent + 独立 Verifier**（更可控可并行），并用 **JSON mode 强约束输出**替代其纯正则解析
  （规避 Researcher repo 里 `\boxed` 正则易崩的坑）。
- 采用 OpenReviewer 的"对齐目标刊分数分布"做校准（CalibrationAgent，待实装）。
- 关键维度（novelty/verify）做**多 provider 投票**（不同模型抓错互补，并集抓错率 83.3%）。

## 证据 / 反例
- 支持独立优先：AgentReview 互见→标准差 -27.2%、偏见溢出 0.25。
- 支持对抗核验：FactReview 执行代码改变 17% claim 判定。
- 支持校准：OpenReviewer 微调后 Exact-Match 55.5% vs 23.8%、平均误差 0.96 vs 2.34。
- 反例/警示：rebuttal 对决策几乎无影响（去掉整段 rebuttal 决策几乎不变）→ 若启用交互必须设计成
  真正影响结论，否则只增成本。

## 移植提示
- 换学科/期刊：只新增 `config/journals/<venue>.yaml`（照 `_template.yaml`），代码不动。
- 换模型后端：改 `.env.cloubic` 的 provider 降级链 + `config/agents.yaml` 的角色→provider 映射。
- 移到别的 OpenAI 兼容环境：`src/paper_reviews/{cloubic,llm_client}.py` 可整体搬走，
  只依赖 httpx + 环境变量。
- 接 RAG 查新/代码执行：在 `orchestrator._run_verification` 注入检索/沙箱执行后端即可，
  接口已留（Verifier 接收 context 字符串）。
