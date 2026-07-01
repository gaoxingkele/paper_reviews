#!/usr/bin/env bash
set -u
cd /d/aicoding/paper_reviews
export PYTHONIOENCODING=utf-8 PYTHONPATH=src
export PR_FORCE_PROVIDER=deepseek PR_LLM_TIMEOUT=120 PR_LLM_RETRIES=2
export CLOUBIC_ROUTED_PROVIDERS=claude,gemini,openai,glm,qwen,grok
PY="D:/Python314/python.exe"
DIR="D:/BaiduSyncdisk/2026-06/科东论文3篇"
VEN="ieee_access,mdpi_energies,mdpi_electronics,mdpi_applied_sciences"

echo "########## A. 补齐 5 篇正样本 (DeepSeek, 清洗版, 单刊 Energies) ##########"
for name in en18010018 en19010140 en19061578 en19092234 en19112570; do
  echo "======== POS $name ========"
  "$PY" scripts/run_review.py "corpus/energies_clean/${name}.txt" --venue mdpi_energies \
        --no-verify --no-critic --out "corpus/eval/${name}__mdpi_energies.md" 2>"corpus/eval/${name}.log"
  tail -1 "corpus/eval/${name}.log" 2>/dev/null
done

echo "########## B. P2/P3 跨刊 (DeepSeek) ##########"
"$PY" scripts/run_review.py "$DIR/paper2(Investigating the Value of LODF-Based Physics).pdf" \
     --venues "$VEN" --no-critic --out "output/P2_LODF__deepseek_cross.md" 2>"output/P2_deepseek.log"
tail -1 output/P2_deepseek.log
"$PY" scripts/run_review.py "$DIR/paper_20260619181714.pdf" \
     --venues "$VEN" --no-critic --out "output/P3_KGRAT__deepseek_cross.md" 2>"output/P3_deepseek.log"
tail -1 output/P3_deepseek.log
echo "ALL_DEEPSEEK_DONE"
