#!/usr/bin/env bash
# 评估 20 篇 Energies 已发表正样本（单刊 mdpi_energies，关核验/自评省成本）
set -u
cd /d/aicoding/paper_reviews
export PYTHONIOENCODING=utf-8 PYTHONPATH=src PR_FORCE_PROVIDER=claude
PY="D:/Python314/python.exe"
mkdir -p corpus/eval
for f in corpus/energies/*.txt; do
  name=$(basename "$f" .txt)
  out="corpus/eval/${name}__mdpi_energies.md"
  if [ -f "${out%.md}.json" ]; then echo "skip $name (done)"; continue; fi
  echo "================ EVAL $name ================"
  "$PY" scripts/run_review.py "$f" --venue mdpi_energies --no-verify --no-critic \
        --out "$out" 2>"corpus/eval/${name}.log"
  tail -1 "corpus/eval/${name}.log" 2>/dev/null
done
echo "ALL_POS_EVAL_DONE"
