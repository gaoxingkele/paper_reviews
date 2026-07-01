"""Translate an MDPI review (from *__cross.json) to Chinese and render a .docx.

Only the free-text fields that go into the document are translated (meta summary,
strengths, and the major/minor findings' issue/reviewer_voice/evidence/fix), so
the call count stays small. Labels/ratings come from report_docx's zh templates.
"""
from __future__ import annotations
import argparse, copy, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from paper_reviews.llm_client import chat            # noqa: E402
from paper_reviews.report_docx import render_mdpi_review_docx  # noqa: E402

import re

SYS = ("你是学术翻译，把英文审稿意见准确译成简体中文，保持专业、客观、可操作；"
       "保留专业术语与缩写（如 NSGA-II, IEEE 30-bus, pymoo, DORA, RRI, HV, IGD, B-loss）原文；"
       "不增删信息、不评论。")

_MARK = "=====SEG{n}====="
_MARK_RE = re.compile(r"=====SEG(\d+)=====")


def translate_batch(items: list[str]) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    B = 8
    for i in range(0, len(items), B):
        chunk = items[i:i + B]
        blocks = "\n".join(f"{_MARK.format(n=j)}\n{s}" for j, s in enumerate(chunk))
        user = ("下面是若干段英文，每段以一行标记 =====SEGk===== 开头。"
                "请逐段翻译为简体中文，并用完全相同的标记输出，标记下一行起为该段译文。"
                "不要输出标记和译文以外的任何内容。\n\n" + blocks)
        import os
        res = chat(os.getenv("PR_TRANSLATE_PROVIDER", "claude"), SYS, user, temperature=0.1)
        # split the response on the SEG markers
        parts = _MARK_RE.split(res.text)
        # parts = [pre, idx0, text0, idx1, text1, ...]
        got = {}
        for k in range(1, len(parts) - 1, 2):
            try:
                got[int(parts[k])] = parts[k + 1].strip()
            except ValueError:
                pass
        for j in range(len(chunk)):
            out.append(got.get(j) or chunk[j])
        print(f"  translated {min(i+B,len(items))}/{len(items)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json", help="path to *__cross.json")
    ap.add_argument("--venue", default="mdpi_energies")
    ap.add_argument("--title", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    d = copy.deepcopy(data)
    # adapt single-venue ReviewReport shape -> cross-journal shape the renderer expects
    if "meta_reviews" not in d and d.get("meta_review") is not None:
        d["meta_reviews"] = {args.venue: d["meta_review"]}
    if "risks" not in d and d.get("risk") is not None:
        d["risks"] = [d["risk"]]
    meta = (d.get("meta_reviews", {}) or {}).get(args.venue, {}) or {}

    # collect strings + remember where to put them back
    strings: list[str] = []
    slots: list = []  # (container, key/index)

    def grab(container, key):
        v = container.get(key) if isinstance(container, dict) else container[key]
        if v:
            slots.append((container, key)); strings.append(v)

    if meta.get("summary"):
        grab(meta, "summary")
    for idx in range(len(meta.get("key_strengths", []))):
        slots.append((meta["key_strengths"], idx)); strings.append(meta["key_strengths"][idx])

    for r in d.get("dimension_reviews", []):
        for f in r.get("findings", []):
            if f.get("severity", 0) >= 2:
                for k in ("issue", "reviewer_voice", "evidence", "fix_suggestion"):
                    if f.get(k):
                        slots.append((f, k)); strings.append(f[k])

    print(f"translating {len(strings)} strings via claude ...")
    zh = translate_batch(strings)
    for (container, key), text in zip(slots, zh):
        container[key] = text

    out = render_mdpi_review_docx(d, args.venue, args.out,
                                  manuscript_title=args.title, lang="zh")
    print("written:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
