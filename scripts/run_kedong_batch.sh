#!/usr/bin/env bash
# 批量跑科东 3 篇 × (IEEE Access + MDPI 三刊) 跨刊评审
set -u
cd /d/aicoding/paper_reviews
export PYTHONIOENCODING=utf-8 PYTHONPATH=src PR_FORCE_PROVIDER=claude
PY="D:/Python314/python.exe"
DIR="D:/BaiduSyncdisk/2026-06/科东论文3篇"
VEN="ieee_access,mdpi_energies,mdpi_electronics,mdpi_applied_sciences"

declare -A PAPERS=(
  ["P1_KE-NSGA-II"]="Paper1Knowledge_Enhanced_NSGA_II_for_Multi_Objective_Economic_Emission_Dispatch.pdf"
  ["P2_LODF"]="paper2(Investigating the Value of LODF-Based Physics).pdf"
  ["P3_KGRAT"]="paper_20260619181714.pdf"
)

for tag in P1_KE-NSGA-II P2_LODF P3_KGRAT; do
  echo "================ $tag : ${PAPERS[$tag]} ================"
  "$PY" scripts/run_review.py "$DIR/${PAPERS[$tag]}" --venues "$VEN" \
        --no-critic --out "output/${tag}__cross.md" 2>"output/${tag}.log"
  echo "---- $tag stderr tail ----"; tail -3 "output/${tag}.log"
done
echo "ALL_DONE"
