# 知识蒸馏报告 — MDPI Energies 正样本校准

> 正样本 = 15 篇近年已发表（已过同行评审）的 Energies 经济/排放调度·优化论文。
> 它们的共性 = Energies 的实际接受门槛；它们在本系统的评分 = 校准信号。

## 1. 校准信号（系统对正样本是否偏严）

- 正样本 RRI：均值 **53.7**，中位 **55**，区间 [14, 69]（P25=49, P75=68）
- AC 推荐分布：{'major_revision': 14, 'minor_revision': 1}
- **14/15 篇被判 major/reject**——但它们全部已发表。说明系统【绝对尺度偏严】，需把 Energies 的尺度锚定到真实接受分布。

### 各维度平均风险分（0–4，越高=系统越爱挑该维度）

| 维度 | 正样本平均风险 |
|---|---|
| novelty | 2.93 |
| soundness | 2.03 |
| experiments | 1.85 |
| reproducibility | 1.75 |
| related_work | 1.85 |
| clarity | 2.35 |
| ethics | 1.59 |

novelty / clarity 在已发表论文上仍被打到偏高分 → 这两维是系统【过度严格】的主因，应在 Energies 下放松。

## 2. P1（你的 KE-NSGA-II）在接受分布中的位置

- P1 对 Energies 的 RRI = **62**，处于已录用论文分布的 **第 60 百分位**。
- 解读：**属于已录用论文的正常区间，并非离群高风险**（已发表论文中位 55，最高 69）。
- 即：之前'偏高/reject'是【绝对尺度】判断；按【真实接受尺度】，P1 与已发表论文相当。

## 3. 接受画像（已发表 Energies 论文的共性）

### 常见测试系统/算例
ies×1515, microgrid×438, integrated energy system×132, real world×57, distribution network×46, ieee 30 bus×38, ieee 57 bus×27, 28 bus×23, ieee 118 bus×16, 57 bus×13, ieee 33 bus×11, micro grid×8

### 常见对比基线/求解器
PSO×105, DE×82, SSA×59, GA×57, PARTICLE SWARM×45, MIXEDINTEGER×37, GENETIC ALGORITHM×24, REINFORCEMENT LEARNING×17, GWO×17, CPLEX×15, TLBO×14, GUROBI×12, DIFFERENTIAL EVOLUTION×10, MIXED INTEGER×9, WOA×9

### 统计严谨性：10/15 篇含显著性检验/多次运行/方差等
### 数据可用性声明：14/15 篇出现 data/code availability 字样

### 审稿系统在这些已录用论文上仍认可的优点（节选，去重前 20 条）

- 论文明确声明聚焦2018–2023年文献（Section 1），相较于仅覆盖传统方法的早期综述（如引用[6]的1977年IEEE综述），时间范围具有一定的当代性，对读者了解近5年EDP研究动态有参考价值。
- 论文提出了一个四维分类框架（传统数学方法、不确定性建模、AI技术、混合算法，见Figure 3），并在此基础上叠加了VPP和MES两类现代电力系统场景（Section 3），这种'系统演化×算法类型'的双轴分类在现有综述中有一定组织创新。
- 论文采用PRISMA系统综述方法（Section 2），明确记录了检索策略（Scopus数据库、关键词、筛选流程，从5070篇到175篇），提升了综述方法论的透明度和可重复性，符合Energies对系统综述的规范要求。
- 论文在Section 6明确识别出两个研究空白：(1)单案例研究主导导致泛化性不足；(2)系统选择任意性导致跨研究比较困难，并呼吁建立标准化评估框架，这一批判性视角具有一定的实践指导价值。
- The paper provides a clear organizational structure with a logical progression from conventional EDP to VPP-based and MES-based dispatch (Sections 3.1→3.2→3.3), making the evolution of the field easy to follow for readers.
- The dual classification framework—categorizing by problem formulation (Section 4: single vs. multi-objective) and by optimization technique (Section 5: conventional, uncertainty, AI, hybrid)—provides a useful mental model for researchers entering the field.
- The PRISMA-based systematic methodology (Section 2) with explicit keyword selection, database filtering steps, and quantified article counts (5070→4481→889→288→175) enhances transparency and reproducibility of the review process.
- Tables 2, 3, and 4 provide structured summaries of distributed EDPs, single-objective, and multi-objective approaches respectively, offering readers quick reference points for comparing studies.
- 作者明确披露资助来源：'This research was funded by the American University of Sharjah through providing a Graduate Research Assistantship (GTA) to the first author... also supported, in part, by the Open Access Program from the American University of Sharjah.'（Funding 部分），符合 MDPI 透明度要求
- 作者声明无利益冲突：'The authors declare no conflict of interest.'（Conflicts of Interest 部分），且补充说明 'This paper represents the opinions of the author(s) and does not mean to represent the position or opinions of the American University of Sharjah'，体现学术独立性
- 采用 PRISMA 系统评价指南（Section 2）进行文献检索与筛选，方法论透明：'employs a systematic literature review that utilizes Preferred Reporting Items for Systematic Reviews and Meta-Analyses (PRISMA) guidelines'，检索策略、纳入/排除标准、最终纳入 175 篇文献的流程可追溯
- 引用文献量达 200 篇（References 列出至 Abdullah et al.），且从摘要和正文判断主要集中在 2018–2023 年（'restricted the publication years to 2018–2023'），符合 MDPI 对近期文献（近 5 年为主）的偏好
- 无明显的图表裁剪迹象：Figure 1（能源占比饼图）、Figure 2–4（流程图/分类树）均为作者自绘示意图或基于公开数据（'The data of US energy sources in 2022 [1], have been utilized to create Figure 1'），Table 1–4 为文献综述归纳表格，未发现选择性展示单一实验结果的操作
- The paper attempts to combine three elements—trip-chain-based EV charging demand modeling, scenario-based robust optimization over time (ROOT-CCFV), and integrated demand response—into a unified multi-regional IES scheduling framework, which represents a reasonable integration effort (Section 1, contributions list).
- The introduction of two new evaluation metrics (Feasible Direction and Stability Degree, Eqs. 22–23 in Section 4.2.2) to the ROOT framework is a tangible algorithmic modification that distinguishes ROOT-CCFV from prior ROOT variants (references [31,32,35,36]).
- The EV trip chain model based on Markov chain spatial transition (Section 3, Eqs. 10–16) distributes charging demand across multiple regions rather than aggregating at a single point, which is a more realistic representation than the 'EV as a whole' baseline.
- The trip-chain-based EV charging model (Section 3) distributes charging demand across multiple regions rather than concentrating it at a single location, which is a more realistic representation and produces spatially differentiated charging profiles (Figure 9).
- The overall RIES framework (Section 2, Figures 1-2) is logically structured with clear energy flow paths, and the SESS constraints (Eqs. 1-3) are mathematically consistent with standard energy storage modeling conventions.
- The EV trip chain model (Section 3) appropriately applies Markov chain theory with the memoryless property assumption (Eq. 10-11), and the use of NHTS data (Table 1) provides an empirical basis for spatial transition probabilities.
- The optimization model (Section 5) is formulated as a well-defined MILP with clearly stated objective function components (Eqs. 24-28) and operational constraints (Eq. 29-30), and the use of CPLEX as a solver ensures global optimality for the linearized problem.

## 4. 据此落地的校准动作

1. `config/journals/mdpi_energies.yaml`：写入真实接受 RRI 分布作为校准锚点；下调 novelty/clarity 的 strictness（已发表论文在这两维仍被打高，说明系统过苛）。
2. 更新 exemplars：用真实已录用样本的 RRI 区间作为 accept/minor 锚点。
3. `mdpi_energies_accepted_profile.md`：接受画像，注入审稿 prompt 作为'该刊实际接受长这样'的参照。
4. scoring 增加百分位解读：报告论文 RRI 在'已录用分布'中的位置，而非只给绝对档。