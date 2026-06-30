#!/usr/bin/env bash
set -u
cd /d/aicoding/paper_reviews
export PYTHONIOENCODING=utf-8 PYTHONPATH=src PR_FORCE_PROVIDER=claude PR_LLM_TIMEOUT=120 PR_LLM_RETRIES=2
PY="D:/Python314/python.exe"
for name in en17215427 en18010018 en19010140 en19020545 en19061425 en19061578 en19092234 en19112570; do
  out="corpus/eval/${name}__mdpi_energies.md"
  [ -f "${out%.md}.json" ] && { echo "skip $name"; continue; }
  echo "================ EVAL $name (clean) ================"
  "$PY" scripts/run_review.py "corpus/energies_clean/${name}.txt" --venue mdpi_energies \
        --no-verify --no-critic --out "$out" 2>"corpus/eval/${name}.log"
  tail -1 "corpus/eval/${name}.log" 2>/dev/null
done
echo "ALL_REMAIN_DONE"
