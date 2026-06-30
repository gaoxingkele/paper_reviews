"""Distill an 'Energies acceptance profile' from the 20 published positive samples.

For each accepted paper we extract a compact, structured trait record (one LLM
call) describing WHAT an accepted Energies dispatch-optimization paper actually
looks like: test systems, baselines compared, statistical practice, citation
recency, data-availability practice, how novelty/value is framed, experimental
scope, and how limitations are handled. We then aggregate these into a knowledge
doc that can be injected into the reviewer prompt as a venue-calibrated anchor,
and into mdpi_energies.yaml exemplars.

Positive samples = papers that PASSED Energies peer review, so their shared
traits define the bar the reviewer should calibrate to.
"""
from __future__ import annotations
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from paper_reviews.llm_client import chat            # noqa: E402

CORPUS = ROOT / "corpus" / "energies"
OUT = ROOT / "corpus" / "acceptance_traits.json"

SCHEMA_SYS = (
    "你是科研方法分析员。给你一篇【已被 MDPI Energies 录用】的电力系统调度/优化论文全文，"
    "请抽取它的结构化特征（用于学习'什么样的论文能被 Energies 接受'）。"
    "只输出 JSON 对象，字段："
    "test_systems(测试系统/算例,如 IEEE 30-bus/118-bus/实际电网/微网，数组), "
    "baselines(对比的基线算法,数组), "
    "methods(核心方法/算法,数组), "
    "stats_practice(统计严谨性:是否多次运行/方差/显著性检验/无,字符串), "
    "citation_recency(文献时效:近5年占比印象 high/medium/low + 是否过度自引,字符串), "
    "data_availability(是否有数据/代码可用性声明 yes/no/unclear), "
    "contribution_framing(如何叙述创新/价值,1-2句), "
    "experimental_scope(实验规模:单算例/多算例/多场景,字符串), "
    "limitations(是否诚实讨论局限 yes/no + 简述), "
    "domain(细分领域,如经济排放调度/低碳调度/最优潮流/微网调度)。"
)


def extract_one(name: str, text: str) -> dict:
    user = f"论文全文（截断）：\n{text[:60000]}\n\n只输出 JSON。"
    res = chat("claude", SCHEMA_SYS, user, temperature=0.1, response_json=True)
    import re
    t = res.text.strip()
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        return json.loads(m.group(0)) if m else {"_raw": t[:500]}


def main():
    files = sorted(CORPUS.glob("*.txt"))
    traits = {}
    if OUT.exists():
        traits = json.loads(OUT.read_text(encoding="utf-8"))
    for fp in files:
        name = fp.stem
        if name in traits:
            print("skip", name); continue
        print("extract", name, "...", flush=True)
        try:
            traits[name] = extract_one(name, fp.read_text(encoding="utf-8"))
        except Exception as e:
            print("  ERR", e); traits[name] = {"_error": str(e)}
        OUT.write_text(json.dumps(traits, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\ndone: {len(traits)} traits -> {OUT}")


if __name__ == "__main__":
    main()
