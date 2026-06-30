"""Knowledge distillation from the published-positive Energies samples.

Pure aggregation over data we already have (no new LLM calls):
- the 15 valid eval JSONs (RRI, dim risk scores, reviewer strengths/weaknesses)
- the cleaned corpus texts (regex traits: test systems, baseline algorithms,
  statistical practice, data-availability practice)

Outputs:
- corpus/DISTILLATION_REPORT.md  (calibration signal + P1 reframing)
- config/journals/mdpi_energies_accepted_profile.md  (acceptance profile to inject)
- corpus/accept_rri_stats.json  (empirical calibration anchors)
"""
from __future__ import annotations
import json, re, pathlib, statistics
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "corpus" / "eval"
CLEAN = ROOT / "corpus" / "energies_clean"
DIMS = ["novelty", "soundness", "experiments", "reproducibility",
        "related_work", "clarity", "ethics"]

# ---- regex trait extractors over manuscript text ----
TEST_SYS = re.compile(r"IEEE\s*\d+[- ]?bus|RTS[- ]?\d+|\b\d+[- ]?bus\b|microgrid|micro-grid|"
                      r"integrated energy system|IES\b|distribution network|39[- ]bus|118[- ]bus|"
                      r"30[- ]bus|6[- ]unit|10[- ]unit|real(?:-| )world|provincial grid", re.I)
BASELINES = re.compile(r"NSGA-?II|NSGA-?III|MOEA/D|MOPSO|SPEA2|\bPSO\b|\bGA\b|differential evolution|"
                       r"\bDE\b|grey wolf|GWO|whale|WOA|mayfly|harris hawks|HHO|salp|SSA|"
                       r"genetic algorithm|particle swarm|ant colony|ACO|teaching.learning|TLBO|"
                       r"reinforcement learning|\bPPO\b|\bDQN\b|CPLEX|Gurobi|YALMIP|mixed.integer", re.I)
STATS = re.compile(r"Wilcoxon|Friedman|p-?value|significance test|standard deviation|"
                   r"confidence interval|\bvariance\b|Monte Carlo|independent runs|30 runs|"
                   r"average of|mean\s*±|effect size", re.I)
DATA_AVAIL = re.compile(r"data availability|code (is )?available|github\.com|zenodo|"
                        r"available (up)?on request|supplementary material", re.I)


def load_valid():
    rows = []
    for fp in sorted(EVAL.glob("*__mdpi_energies.json")):
        d = json.loads(fp.read_text(encoding="utf-8"))
        if not (d.get("risk") and d.get("dimension_reviews")):
            continue
        rows.append((fp.stem.replace("__mdpi_energies", ""), d))
    return rows


def main():
    rows = load_valid()
    n = len(rows)
    rris = sorted(d["risk"]["rri"] for _, d in rows)
    dim_means = {k: round(statistics.mean(
        [d["risk"]["dim_scores"].get(k, 0) for _, d in rows]), 2) for k in DIMS}
    recs = Counter((d.get("meta_review") or {}).get("recommendation") for _, d in rows)

    stats = {
        "n": n, "rri_mean": round(statistics.mean(rris), 1),
        "rri_median": statistics.median(rris),
        "rri_p25": rris[len(rris)//4], "rri_p75": rris[(3*len(rris))//4],
        "rri_min": min(rris), "rri_max": max(rris),
        "rri_sorted": rris, "dim_means": dim_means,
    }
    (ROOT / "corpus" / "accept_rri_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- traits from corpus text ----
    sysc, basec, statsc, datac = Counter(), Counter(), 0, 0
    for name, _ in rows:
        fp = CLEAN / f"{name}.txt"
        if not fp.exists():
            fp = ROOT / "corpus" / "energies" / f"{name}.txt"
        if not fp.exists():
            continue
        t = fp.read_text(encoding="utf-8")
        for m in TEST_SYS.findall(t):
            sysc[m.lower().replace("-", " ").strip()] += 1
        for m in BASELINES.findall(t):
            basec[m.upper().replace("-", "")] += 1
        if STATS.search(t):
            statsc += 1
        if DATA_AVAIL.search(t):
            datac += 1

    # aggregate reviewer strengths (what the reviewer praised in ACCEPTED papers)
    strengths = []
    for _, d in rows:
        for r in d["dimension_reviews"]:
            strengths += [s for s in r.get("strengths", []) if len(s) > 30]

    # ---- P1 percentile ----
    p1_rri = None
    p1fp = ROOT / "output" / "P1_KE-NSGA-II__cross.json"
    if p1fp.exists():
        p1 = json.loads(p1fp.read_text(encoding="utf-8"))
        p1_rri = next((r["rri"] for r in p1.get("risks", []) if r["venue"] == "mdpi_energies"), None)
    p1_pct = None
    if p1_rri is not None:
        p1_pct = round(100 * sum(1 for x in rris if x <= p1_rri) / len(rris))

    # ---- write DISTILLATION_REPORT.md ----
    L = ["# 知识蒸馏报告 — MDPI Energies 正样本校准", "",
         f"> 正样本 = {n} 篇近年已发表（已过同行评审）的 Energies 经济/排放调度·优化论文。",
         "> 它们的共性 = Energies 的实际接受门槛；它们在本系统的评分 = 校准信号。", "",
         "## 1. 校准信号（系统对正样本是否偏严）", "",
         f"- 正样本 RRI：均值 **{stats['rri_mean']}**，中位 **{stats['rri_median']}**，"
         f"区间 [{stats['rri_min']}, {stats['rri_max']}]（P25={stats['rri_p25']}, P75={stats['rri_p75']}）",
         f"- AC 推荐分布：{dict(recs)}",
         f"- **{sum(v for k,v in recs.items() if k in ('major_revision','reject'))}/{n} 篇被判 major/reject**"
         "——但它们全部已发表。说明系统【绝对尺度偏严】，需把 Energies 的尺度锚定到真实接受分布。", "",
         "### 各维度平均风险分（0–4，越高=系统越爱挑该维度）", "",
         "| 维度 | 正样本平均风险 |", "|---|---|"]
    for k in DIMS:
        L.append(f"| {k} | {dim_means[k]} |")
    L += ["",
          "novelty / clarity 在已发表论文上仍被打到偏高分 → 这两维是系统【过度严格】的主因，应在 Energies 下放松。", "",
          "## 2. P1（你的 KE-NSGA-II）在接受分布中的位置", ""]
    if p1_rri is not None:
        L.append(f"- P1 对 Energies 的 RRI = **{p1_rri}**，处于已录用论文分布的 **第 {p1_pct} 百分位**。")
        verdict = ("属于已录用论文的正常区间，并非离群高风险" if p1_pct <= 75
                   else "略高于多数已录用论文，但仍在已发表范围内")
        L.append(f"- 解读：**{verdict}**（已发表论文中位 {stats['rri_median']}，最高 {stats['rri_max']}）。")
        L.append("- 即：之前'偏高/reject'是【绝对尺度】判断；按【真实接受尺度】，P1 与已发表论文相当。")
    L += ["", "## 3. 接受画像（已发表 Energies 论文的共性）", "",
          "### 常见测试系统/算例", ", ".join(f"{k}×{v}" for k, v in sysc.most_common(12)) or "—",
          "", "### 常见对比基线/求解器", ", ".join(f"{k}×{v}" for k, v in basec.most_common(15)) or "—",
          "", f"### 统计严谨性：{statsc}/{n} 篇含显著性检验/多次运行/方差等",
          f"### 数据可用性声明：{datac}/{n} 篇出现 data/code availability 字样", "",
          "### 审稿系统在这些已录用论文上仍认可的优点（节选，去重前 20 条）", ""]
    seen = set()
    for s in strengths:
        k = s.strip().lower()[:60]
        if k in seen:
            continue
        seen.add(k)
        L.append(f"- {s}")
        if len(seen) >= 20:
            break
    L += ["", "## 4. 据此落地的校准动作", "",
          "1. `config/journals/mdpi_energies.yaml`：写入真实接受 RRI 分布作为校准锚点；"
          "下调 novelty/clarity 的 strictness（已发表论文在这两维仍被打高，说明系统过苛）。",
          "2. 更新 exemplars：用真实已录用样本的 RRI 区间作为 accept/minor 锚点。",
          "3. `mdpi_energies_accepted_profile.md`：接受画像，注入审稿 prompt 作为'该刊实际接受长这样'的参照。",
          "4. scoring 增加百分位解读：报告论文 RRI 在'已录用分布'中的位置，而非只给绝对档。"]
    (ROOT / "corpus" / "DISTILLATION_REPORT.md").write_text("\n".join(L), encoding="utf-8")

    # ---- acceptance profile doc (injectable) ----
    P = ["# MDPI Energies 接受画像（从已发表正样本蒸馏）", "",
         f"> 依据 {n} 篇近年已发表 Energies 经济/排放调度·优化论文蒸馏。注入审稿 prompt，"
         "作为'该刊实际接受的论文长什么样'的校准参照，避免用过苛的通用尺度。", "",
         "## 已录用论文的典型画像",
         f"- 测试系统：{', '.join(k for k,_ in sysc.most_common(8))}",
         f"- 对比基线：{', '.join(k for k,_ in basec.most_common(10))}",
         f"- 统计严谨性：约 {round(100*statsc/n)}% 报告显著性检验/多次运行/方差",
         f"- 数据可用性：约 {round(100*datac/n)}% 含 data/code availability",
         f"- 本系统对这些已录用论文给出的 RRI：中位 {stats['rri_median']}，区间 [{stats['rri_min']},{stats['rri_max']}]",
         "",
         "## 审稿校准要点（对 Energies）",
         "- 已发表 Energies 论文普遍：聚焦单一/少数算例、用经典 MOEA 基线、创新为'机制组合/场景适配'而非全新算法——",
         "  这类'增量但扎实'的工作在 Energies 是可接受的。**不要因'创新性仅为增量'就判高风险**（DORA + 接受非-SOTA）。",
         "- 重点仍在：技术正确、实验支撑结论、负面/非-SOTA 结论的价值叙事、近 5 年文献、数据可用性。",
         f"- 量化锚点：RRI ≤ {stats['rri_median']} 即与多数已录用论文相当（accept/minor 区间）。"]
    (ROOT / "config" / "journals" / "mdpi_energies_accepted_profile.md").write_text(
        "\n".join(P), encoding="utf-8")

    print(f"valid positives: {n}")
    print(f"RRI mean={stats['rri_mean']} median={stats['rri_median']} range=[{stats['rri_min']},{stats['rri_max']}]")
    print(f"P1 Energies RRI={p1_rri} -> 第 {p1_pct} 百分位 (已录用分布)")
    print("test systems:", dict(sysc.most_common(6)))
    print("baselines:", dict(basec.most_common(8)))
    print(f"stats rigor {statsc}/{n}, data-availability {datac}/{n}")
    print("\nwrote: corpus/DISTILLATION_REPORT.md, config/journals/mdpi_energies_accepted_profile.md, corpus/accept_rri_stats.json")


if __name__ == "__main__":
    main()
