"""CLI: review a manuscript against a journal profile.

Usage:
    python scripts/run_review.py <manuscript_path> --venue ieee_access
    python scripts/run_review.py paper.md --venue ieee_access --no-verify

Outputs a markdown review under output/.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper_reviews.config import list_journals, load_journal      # noqa: E402
from paper_reviews.ingest import load_paper                       # noqa: E402
from paper_reviews.orchestrator import Orchestrator               # noqa: E402
from paper_reviews.report import render_markdown                  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-agent paper review")
    ap.add_argument("manuscript", help="path to .tex/.md/.txt/.pdf")
    ap.add_argument("--venue", required=True, help=f"one of: {', '.join(list_journals()) or '(none yet)'}")
    ap.add_argument("--no-verify", action="store_true", help="skip adversarial verification")
    ap.add_argument("--no-critic", action="store_true", help="skip review self-critique")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--out", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    paper = load_paper(args.manuscript)
    print(f"[ingest] {paper.paper_id}: '{paper.title[:60]}' "
          f"({paper.source_format}, {len(paper.sections)} sections)")

    orch = Orchestrator(args.venue,
                        run_verification=not args.no_verify,
                        run_critic=not args.no_critic,
                        parallel=args.parallel)
    rep = orch.review(paper)

    md = render_markdown(rep, load_journal(args.venue))
    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    out_md = Path(args.out) if args.out else out_dir / f"{paper.paper_id}__{args.venue}.md"
    out_md.write_text(md, encoding="utf-8")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(json.dumps(asdict(rep), ensure_ascii=False, indent=2,
                                   default=str), encoding="utf-8")

    mr = rep.meta_review
    print(f"[done] recommendation={mr.recommendation if mr else 'n/a'} "
          f"score={mr.overall_score if mr else 'n/a'} "
          f"human_review={mr.needs_human_review if mr else 'n/a'}")
    print(f"[out] {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
