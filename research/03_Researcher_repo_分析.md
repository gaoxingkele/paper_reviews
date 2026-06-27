# Researcher 仓库工程分析（zhu-minjun/Researcher）

> 目的：为我们自研的「多智能体审稿系统（Python + httpx + OpenAI 兼容）」提取可复用的能力、prompt、数据结构与评测方法。
> 本地路径：`D:\aicoding\paper_reviews\references\Researcher\`
> 论文：CycleResearcher (ICLR 2025, arXiv:2411.00816)、DeepReview (arXiv:2503.08569, ACL 2025)
> 注意：DeepReviewer-v2 已另起仓库 `ResearAI/DeepReviewer-v2`，在线平台 deepscientist.cc / 已不在本仓库。

---

## 0. 一句话总览

这是一个「论文生成 ↔ 论文审稿」闭环的开源生态，三大组件：

| 组件 | 作用 | 关键文件 |
|---|---|---|
| **CycleResearcher** | 根据参考文献生成完整论文（LaTeX + 实验设计 JSON） | `ai_researcher/cycle_researcher.py` |
| **CycleReviewer** | 给定论文文本，产出 4 份结构化审稿意见 + 接受/拒稿决策 | `ai_researcher/cycle_reviewer.py` |
| **DeepReviewer** | 多视角（N 个 reviewer）模拟 + 自我验证 + 可选检索增强的「深度思考」审稿 | `ai_researcher/deep_reviewer.py` |
| **AIDetector** | Fast-DetectGPT 检测文本是否 AI 生成 | `ai_researcher/detector.py`, `ai_researcher/detect/` |

**对我们最重要的结论**：核心价值不在模型权重（都是本地 vLLM 跑的微调 Llama/Qwen/Mistral），而在于
**(a) 审稿的 prompt 组织方式（多 reviewer + self-verification + 检索增强的三档模式）**、
**(b) 输出 schema（`\boxed_*{}` 包裹的结构化分块）**、
**(c) 评测方法学（代理 MSE/MAE、Spearman、pairwise 排序准确率、决策准确率、LLM-as-judge win-rate）**。
这三样可以完全脱离它的权重，直接搬到我们「OpenAI 兼容 API + httpx」的架构里。

---

## 1. 与审稿相关的能力 / 模型一览

### 1.1 CycleReviewer（单轮、固定 4 reviewer）
- 出处：`ai_researcher/cycle_reviewer.py`
- 模型映射（本地 vLLM 加载）：
  - `8B` → `WestlakeNLP/CycleReviewer-ML-Llama3.1-8B`
  - `70B` → `WestlakeNLP/CycleReviewer-ML-Llama3.1-70B`
  - `123B` → `WestlakeNLP/CycleReviewer-ML-Pro-123B`
- 调用：
  ```python
  reviewer = CycleReviewer(model_size="8B")
  review_results = reviewer.evaluate(paper_text)   # paper_text: str 或 list[str]
  print(review_results[0]['avg_rating'])           # 平均分
  print(review_results[0]['paper_decision'])       # 'Accept' / 'Reject'
  ```
- **输入**：论文全文（字符串；实际是 LaTeX 拼接的 paper_context）。
- **输出**：`get_reviewer_score()` 解析出的 dict，字段见 §2.4。
- 采样参数：`temperature=0.4, top_p=0.95, max_tokens=7000`，batch_size=10。
- system prompt 要求「填写 **4** 份审稿意见」（固定 4 个 reviewer）。

### 1.2 DeepReviewer（多模式、可变 reviewer 数、自验证、检索增强）
- 出处：`ai_researcher/deep_reviewer.py`
- 模型：`7B` / `14B`（`WestlakeNLP/DeepReviewer-7B|14B`），`max_model_len=90000`。
- 三种模式（核心差异在 system prompt 与是否多步调用，见 §2.1）：
  - **Fast Mode**：直接出审稿，无多 reviewer。
  - **Standard Mode**：模拟 N 个 reviewer + self-verification + 汇总 meta review。（默认）
  - **Best Mode**：在 Standard 基础上，先让模型**提出 3 个检索问题** → 调 OpenScholar 检索 → 把检索结果回灌做第二轮生成（RAG 两步调用）。
- 调用：
  ```python
  deep_reviewer = DeepReviewer(model_size="14B")
  res = deep_reviewer.evaluate(paper_text, mode="Standard Mode", reviewer_num=4)
  for rv in res[0]['reviews']:
      print(rv.get('rating'), rv.get('summary'))
  # Best Mode 还能 enable_search / self_verification
  ```
- **输入**：论文全文；`mode`、`reviewer_num`、`max_tokens`（默认 35000）。
- **输出**：`_parse_review()` 产出的 dict：`{raw_text, reviews:[...], meta_review:{...}, decision}`，见 §2.3。

### 1.3 OpenScholar（Best Mode 的检索后端，可选）
- 目录 `OpenScholar/`，是一个 RAG 学术问答服务（Semantic Scholar API + reranker）。
- DeepReviewer 通过 HTTP `POST http://127.0.0.1:38015/batch_ask {"questions":[...]}` 调它（`deep_reviewer.py:retrieve_information`）。
- 我们可以**用任意自己的检索/搜索后端替换**这个接口（它只要求返回 `results[i].output` 和 `results[i].final_passages`）。

---

## 2. 评审是如何组织的（真实 prompt / schema / 字段）

### 2.1 DeepReviewer 的 system prompt（真实摘录，`deep_reviewer.py:_generate_system_prompt`）

所有模式共享一句「reviewer 写作顺序」约束：
```
When you simulate different reviewers, write the sections in this order:
Summary, Soundness, Presentation, Contribution, Strengths, Weaknesses, Suggestions, Questions, Rating and Confidence.
```

**Standard Mode**：
```
You are an expert academic reviewer tasked with providing a thorough and balanced
evaluation of research papers. Your thinking mode is Standard Mode. In this mode, you
should review by simulating {reviewer_num} different reviewers, and use self-verification
to double-check any paper deficiencies identified. Finally, provide complete review results.
```

**Best Mode**（多了「先提 3 个检索问题，我帮你搜」+ self-verification）：
```
... Your thinking mode is Best Mode. In this mode, you should aim to provide the most
reliable review results by conducting a thorough analysis of the paper. I allow you to use
search tools to obtain background knowledge about the paper - please provide three different
questions. I will help you with the search. After you complete your thinking, you should
review by simulating {reviewer_num} different reviewers, and use self-verification to
double-check any paper deficiencies identified. Finally, provide complete review results.
```

**Fast Mode**：
```
... Your thinking mode is Fast Mode. In this mode, you should quickly provide the review results.
```

### 2.2 输出用 `\boxed_*{}` 分块包裹（真实输出，取自 `evaluate/DeepReview/sample.json`）

模型输出是「思维链 + 三种 boxed 块」混排的纯文本，下游用正则切。三种块：

- `\boxed_questions{ ... }` —— Best Mode 第一步产出的检索问题（每行一个问题）。
- `\boxed_simreviewers{ ... }` —— N 个 reviewer 的意见，内部以 `## Reviewer 1 / ## Reviewer 2 ...` 分隔，每个 reviewer 内用 **`### 三级标题`** 分小节。
- `\boxed_review{ ... }` —— 自我验证后汇总的**最终 meta review**，内部用 **`## 二级标题`** 分小节，末尾带 `## Rating`、`## Confidence`、`## Decision`。

**单个模拟 reviewer 真实片段**（standard mode）：
```
\boxed_simreviewers{
## Reviewer 1
### Summary
This paper introduces an iterative mask denoising (IMD) approach ...
### Soundness
2 fair
### Presentation
2 fair
### Contribution
2 fair
### Strengths
1. The proposed iterative mask denoising (IMD) process is simple yet effective ...
### Weaknesses
#### comment
1. My primary concern is that the paper lacks a clear definition ...
### Suggestions
...
### Questions
...
### Rating
...
### Confidence
...
}
```
> 注意打分形式是「**数字 + 词**」，如 `2 fair`、`3 good`；Rating 是 1–10，Confidence 是 1–5。

**最终 meta review 真实片段**（self-verification 之后）：
```
Now, I have successfully verified each review. Next, I will organize this content and output the final review decision:

\boxed_review{
## Summary:
This paper introduces MaskComp ...
## Soundness:
...
## Presentation:
...
## Contribution:
...
## Strengths:
...
## Weaknesses:
...
## Suggestions:
...
## Questions:
...
## Rating:
5.75
## Confidence:
4.0
## Decision:
Accept
}
```

**Best Mode 第一步**输出 `step1_output`，含 `\boxed_questions{...}`，例如：
```
\boxed_questions{
How have traditional image segmentation methods evolved over the years ...?
What are the primary challenges and limitations of using conditional image generation ...?
In the context of object completion ...?
}
```

### 2.3 DeepReviewer 解析后的 Python 结构（`deep_reviewer.py:_parse_review`）

```python
{
  "raw_text": "<原始全文>",
  "reviews": [           # 来自 \boxed_simreviewers，每个模拟 reviewer 一项
     {
       "reviewer_id": 1,
       "text": "...",
       "summary": "...", "soundness": "...", "presentation": "...",
       "contribution": "...", "strengths": "...", "weaknesses": "...",
       "suggestions": "...", "questions": "...",
       "rating": 5.0      # 正则抽出的第一个数字, float
     }, ...
  ],
  "meta_review": {        # 来自 \boxed_review（最终汇总）
     "content": "...", "summary": "...", "rating": 5.75,
     "soundness": "...", "presentation": "...", "contribution": "...",
     "strengths": "...", "weaknesses": "...", "suggestions": "...", "questions": "..."
  },
  "decision": "Accept"    # 正则 ## Decision: \n Accept|Reject
}
```
解析关键正则（可直接借鉴）：
- meta：`re.search(r'\\boxed_review\{(.*?)\n}', text, re.DOTALL)`
- 多 reviewer：`re.search(r'\\boxed_simreviewers\{(.*?)\n}', ...)` 再 `re.split(r'## Reviewer \d+', ...)`
- 分节：`re.search(f'## {section}:\\s+(.*?)(?=##|\\Z)', section, re.DOTALL)`
- 数字分：`re.search(r'(\d+(?:\.\d+)?)', rating_text)`
- 决策：`re.search(r'## Decision:\s*\n\s*(\w+)', text)`

### 2.4 CycleReviewer 的 system prompt 与字段（`cycle_reviewer.py` + `utils.py`）

system prompt（真实摘录）要求 9 个维度，并显式「fill out **4** review opinions」：
```
1. Summary  2. Soundness  3. Presentation  4. Contribution  5. Strengths
6. Weaknesses  7. Questions  8. Rating (1-10, justify)  9. Meta Review (Accept/Reject)
```
解析函数 `get_reviewer_score()`（先试 7B 格式 `##`，失败再试 123B 格式 `### / ## Reviewer`），产出：
```python
{
  'content', 'reviews', 'summary'[], 'review_rate'[], 'rating'[float],
  'soundness'[], 'presentation'[], 'contribution'[], 'strength'[],
  'weaknesses'[], 'questions'[], 'flag_for_ethics_review'[], 'confidence'[],
  'paper_decision': 'Accept'|'Reject',
  'meta_review': '...',
  'avg_rating': mean(rating)
}
```
分隔符约定：每份 review 之间用 `**********\n`；`## Paper Decision`、`## Meta Review` 是控制 token。

### 2.5 打分维度总结（我们可直接采用的 rubric）

| 维度 | 量纲 | 说明 |
|---|---|---|
| Soundness | 1–4（数字+词，如 `2 fair`） | 方法/逻辑严谨性 |
| Presentation | 1–4 | 清晰度、组织 |
| Contribution | 1–4 | 新颖性/意义 |
| Rating | 1–10（可小数，meta 会平均出 5.75 之类） | 总分 |
| Confidence | 1–5 | 审稿人信心 |
| Decision | Accept / Reject | 二分类 |
| Flag For Ethics Review | 文本 | 伦理审查标记 |

定性字段：Summary / Strengths / Weaknesses / Suggestions / Questions。

---

## 3. 审稿质量怎么评测（指标 / 一致性 / 数据集）

### 3.1 数据集
- **Review-5K**（CycleReviewer 训练，4189/781）
- **DeepReview-13K**（DeepReviewer 训练，多视角，13378/1286）
- **Research-14K**（生成器训练）
- 评测样例文件：`evaluate/DeepReview/sample.json`（含 `paper_context`、人类 `review[]`（每份有 `content.rating/soundness/presentation/contribution`）、`decision`，以及模型三种模式预测 `pred_fast/standard/best_mode`）。

### 3.2 客观指标（`evaluate/DeepReview/evalate.py`）
以「**人类多位 reviewer 打分的均值**」为代理真值（proxy ground truth），对 Rating/Soundness/Presentation/Contribution 四维分别算：
- **MSE / MAE**（预测分 vs 人类均分）
- **Spearman 相关**（与人类排序的相关性，`scipy.stats.spearmanr`）
- **Pairwise 排序准确率**（任取两篇论文，模型是否能正确判断哪篇分更高，`calculate_pairwise_accuracies`）—— 衡量「比较/排序」能力，比绝对分更鲁棒。
- **Decision Accuracy + Macro-F1**（Accept/Reject 二分类，`precision_recall_fscore_support`）。

readme 自报：CycleReviewer 相比人类 reviewer，Proxy MSE 降 48.77%、MAE 降 26.89%，决策准确率 74.24%。

### 3.3 主观指标：LLM-as-judge win-rate（`evaluate/DeepReview/win_rate_evaluate.py`）
- 用一个**中立仲裁者 LLM**（这里配的是 Gemini 2.0 flash thinking，OpenAI 兼容 client）成对比较两份 review。
- **关键防偏置技巧**：随机交换 A/B 顺序（`random.randint(0,1)` 决定 DeepReviewer 是 A 还是 B），记录 `v.s.` 用于回判 win/lose/tie。
- 评 4 个维度：**Technical Accuracy / Constructive Value / Analytical Depth / Communication Clarity** + Overall。
- 仲裁 prompt（`SYSTEM_PROMPT`）强制「引用论文/review 原文做证据、给推理链、允许 Tie 但要论证」，输出固定格式 `**Better Assistant:** [A or B or Tie]`，再正则统计胜率。
- 这套「**随机化 A/B + 证据驱动 + 维度化 win-rate**」非常值得我们直接抄来做自评/对比实验。

---

## 4. AI 生成内容检测（detector）思路 + 是否集成

### 4.1 原理（`ai_researcher/detect/`，基于 Fast-DetectGPT，作者 Guangsheng Bao）
- 核心量 `sampling_discrepancy_analytic`（`fast_detect_gpt.py`）：用一个 scoring model 算文本每个 token 的 log-likelihood，再用 reference model 的分布算条件均值/方差，得到一个标准化的「条件概率曲率」判据 criterion。**人写文本 criterion 低，模型生成文本 criterion 高**（因为模型生成的恰好落在自己概率分布的高曲率/高似然区）。
- 无需训练分类器、无需扰动重采样（比原版 DetectGPT 快很多），只需对一段文本前向一次。
- 概率换算（`detect/__init__.py:_estimate_probability`）：用预存参考分布（`llama-8B-ref.json` / `DATA_`）里 real/fake 的 criterion 经验分布，做局部 KNN 密度比 `cnt_fake/(cnt_real+cnt_fake)` → 输出 0–1 概率。

### 4.2 调用与输出（`detector.py`）
```python
detector = AIDetector(device='cpu')          # 默认 scoring=ref=Llama-3.1-8B
r = detector.analyze_paper(paper)            # 或 detector.detect(text)
# r = {criterion, probability, is_likely_ai_generated(>0.5),
#      confidence_level: 'Low/Moderate/High/Very high likelihood of AI generation'}
```
阈值分段：<0.3 Low / <0.5 Moderate / <0.7 High / 否则 Very high。

### 4.3 是否值得集成（判断投稿是否 AI 代写）
- **价值**：能给「这篇投稿/这段文本疑似 AI 生成」一个量化分，作为审稿系统的一个 side-signal/risk flag，思路成熟、论文级。
- **代价/限制**：
  1. 需要本地加载一个**白盒 LLM（要 logits）**，OpenAI 兼容 API **拿不到 token logits**，无法直接套到我们 httpx 架构——必须额外起一个本地 HF 模型（transformers + GPU/CPU）。
  2. 对长论文/LaTeX/公式鲁棒性一般（默认 `max_length=2048`，只截一段），且 GPT-4 级新模型检测准确率已普遍下降，**误判风险高，不能作为拒稿硬依据**。
- **建议**：作为**可选的独立微服务**（输入文本→返回 probability），与主审稿流程解耦；仅在 UI 上作为「AI 生成风险提示」展示，不进入打分/决策逻辑。

---

## 5. 可直接借鉴 / 移植到我们架构（httpx + OpenAI 兼容）的清单

> 我们的优势：用 OpenAI 兼容 chat API + httpx，不依赖 vLLM/transformers。下列东西**与权重无关**，可直接迁移。

1. **三档审稿模式的 prompt 体系**（Fast / Standard / Best）——直接复用 `_generate_system_prompt` 的措辞，把「simulate N reviewers + self-verification」写进 system prompt 即可在任意 GPT/Claude/Qwen-API 上跑。
2. **多 reviewer 单次生成 vs 多 agent 多次调用 的两种实现**：原仓库是「一次生成里让模型扮演 N 个 reviewer」（省 token）；我们也可拆成 N 个独立 API agent + 1 个 meta/AC agent 汇总（更可控、可并行 httpx）。两套思路本文都给了模板。
3. **Best Mode 的「自提检索问题 → 检索 → 回灌二轮生成」两步 RAG 流程**（`deep_reviewer.py` 的 step1/step2 message 拼接：`[sys, user(paper), assistant(step1), user(qa_text)]`）——把 OpenScholar 换成我们自己的搜索/向量库即可。
4. **输出 schema：`\boxed_review{}` / `\boxed_simreviewers{}` / `\boxed_questions{}` 包裹 + `##/###` 分节**——这是一种「思维链与结构化结果分离」的稳妥方案；我们可改成更易解析的 JSON / 或保留 boxed + 正则解析（解析器代码可直接拿，见 §2.3）。
5. **打分 rubric**：Soundness/Presentation/Contribution(1–4) + Rating(1–10) + Confidence(1–5) + Decision(Accept/Reject) + Ethics flag，定性字段 Summary/Strengths/Weaknesses/Suggestions/Questions。直接采用，与 ICLR/NeurIPS OpenReview 对齐。
6. **解析器**（`utils.py:get_reviewer_score_*`、`deep_reviewer.py:_parse_review`、`evalate.py:get_pred`）：现成的正则切块代码，可直接改写为我们的 Python 解析模块。
7. **评测脚手架**（`evalate.py`）：proxy-MSE/MAE + Spearman + **pairwise 排序准确率** + decision F1，整套可复用来评我们系统与人类一致性。强烈建议把 pairwise 排序准确率纳入我们的核心指标。
8. **LLM-as-judge win-rate**（`win_rate_evaluate.py`）：随机化 A/B 顺序消偏 + 4 维证据驱动仲裁 prompt + win/tie/lose 统计——直接可用 OpenAI 兼容 client 跑（它本来就是 `openai.Client`）。
9. **self-verification 模式**：让模型在出最终意见前，先生成 N 份初稿再「逐条验证缺陷」后汇总成 meta review——这是提质的关键 prompt 技巧，几乎零成本接入。
10. **代理真值构造法**：以「多位人类 reviewer 打分均值」为回归目标，而非单一标签——做数据集/评测时照搬。
11. **AI 检测作为可选旁路微服务**（§4.3）：独立部署、只产出风险提示，不进决策。
12. **数据集可直接用于冷启动 / few-shot / 微调**：Review-5K、DeepReview-13K（HuggingFace `WestlakeNLP/...`），含真实 OpenReview 风格多视角审稿，可做我们 prompt 的 few-shot 示例或评测集。

---

## 6. 注意点 / 坑

- 本仓库审稿能力**强绑定其微调权重**（vLLM 本地推理）；通用 API 模型直接套同样 prompt，质量未必复现其论文指标，需我们自己做 few-shot / 微调对齐。
- `extract_questions_from_content`（`deep_reviewer.py`）的正则有 bug（`\boxed` 里 `\b` 被当退格符），Best Mode 解析不稳健——我们重写时要修。
- 解析全靠字符串/正则切分，对模型不按格式输出很脆弱；我们用 API 时建议**用 JSON mode / function calling 强约束输出**，比 boxed+正则更稳。
- detector 需要 token-level logits，**OpenAI 兼容 API 不提供**，必须本地 HF 模型，集成成本独立评估。
