"""Collect the positive-sample (published Energies) evaluations and emit the
calibration signal + raw material for the acceptance-profile distillation.

Reads corpus/eval/*.json (single-venue mdpi_energies reviews of accepted papers)
and reports, per paper: RRI, predicted decision, AC recommendation, dim risk
scores. Then aggregates: since these papers ARE published (positive label), a
well-calibrated reviewer should rate most of them accept/minor (low RRI). A
systematic skew to major/reject = the reviewer is too strict and needs
calibration.
"""
from __future__ import annotations
import json, pathlib, statistics

EVAL = pathlib.Path("corpus/eval")
DIMS = ["novelty", "soundness", "experiments", "reproducibility",
        "related_work", "clarity", "ethics"]


def main():
    rows = []
    for fp in sorted(EVAL.glob("*__mdpi_energies.json")):
        d = json.loads(fp.read_text(encoding="utf-8"))
        risk = d.get("risk") or {}
        meta = d.get("meta_review") or {}
        ds = risk.get("dim_scores", {})
        rows.append({
            "name": fp.stem.replace("__mdpi_energies", ""),
            "rri": risk.get("rri"),
            "tier": risk.get("tier"),
            "pred": risk.get("predicted_decision"),
            "rec": meta.get("recommendation"),
            "score": meta.get("overall_score"),
            "dims": ds,
        })
    if not rows:
        print("no eval json yet"); return

    print(f"=== 正样本评估汇总 (n={len(rows)}) ===\n")
    print(f"{'paper':16} {'RRI':>4} {'tier':>5} {'pred':>16} {'AC_rec':>15} {'score':>5}")
    for r in rows:
        print(f"{r['name']:16} {str(r['rri']):>4} {str(r['tier']):>5} "
              f"{str(r['pred']):>16} {str(r['rec']):>15} {str(r['score']):>5}")

    rris = [r["rri"] for r in rows if r["rri"] is not None]
    recs = [r["rec"] for r in rows]
    from collections import Counter
    print("\n--- 校准信号 ---")
    if rris:
        print(f"RRI: mean={statistics.mean(rris):.1f} median={statistics.median(rris)} "
              f"min={min(rris)} max={max(rris)}")
    print("AC 推荐分布:", dict(Counter(recs)))
    # positive should be accept/minor; count "误拒/误大修"
    bad = sum(1 for r in recs if r in ("reject", "major_revision"))
    print(f"被判 major/reject 的正样本: {bad}/{len(rows)}  "
          f"(占 {bad/len(rows)*100:.0f}%) —— 越高说明系统对正样本越偏严")
    print("\n--- 各维度平均风险分 (0-4，越高系统越爱挑该维度的刺) ---")
    for k in DIMS:
        vals = [r["dims"].get(k) for r in rows if r["dims"].get(k) is not None]
        if vals:
            print(f"  {k:16} mean={statistics.mean(vals):.2f}")

    pathlib.Path("corpus/positives_eval_summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nsaved -> corpus/positives_eval_summary.json")


if __name__ == "__main__":
    main()
