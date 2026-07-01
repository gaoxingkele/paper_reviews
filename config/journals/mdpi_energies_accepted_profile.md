# MDPI Energies 接受画像（从已发表正样本蒸馏）

> 依据 20 篇近年已发表 Energies 经济/排放调度·优化论文蒸馏。注入审稿 prompt，作为'该刊实际接受的论文长什么样'的校准参照，避免用过苛的通用尺度。

## 已录用论文的典型画像
- 测试系统：ies, microgrid, integrated energy system, distribution network, real world, ieee 30 bus, ieee 57 bus, 28 bus
- 对比基线：HHO, PSO, NSGAII, DE, SSA, MOPSO, PARTICLE SWARM, GA, MOEA/D, PPO
- 统计严谨性：约 60% 报告显著性检验/多次运行/方差
- 数据可用性：约 95% 含 data/code availability
- 本系统对这些已录用论文给出的 RRI：中位 61.5，区间 [14,76]

## 审稿校准要点（对 Energies）
- 已发表 Energies 论文普遍：聚焦单一/少数算例、用经典 MOEA 基线、创新为'机制组合/场景适配'而非全新算法——
  这类'增量但扎实'的工作在 Energies 是可接受的。**不要因'创新性仅为增量'就判高风险**（DORA + 接受非-SOTA）。
- 重点仍在：技术正确、实验支撑结论、负面/非-SOTA 结论的价值叙事、近 5 年文献、数据可用性。
- 量化锚点：RRI ≤ 61.5 即与多数已录用论文相当（accept/minor 区间）。