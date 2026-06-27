"""paper_reviews — multi-agent, journal-targeted scholarly paper review.

Quickstart:
    from paper_reviews.ingest import load_paper
    from paper_reviews.orchestrator import review_paper
    from paper_reviews.report import render_markdown
    from paper_reviews.config import load_journal

    paper = load_paper("manuscript.md")
    report = review_paper("ieee_access", paper)
    print(render_markdown(report, load_journal("ieee_access")))
"""
from .models import (Paper, ReviewReport, DimensionReview, MetaReview,
                     VerificationResult, Recommendation)

__all__ = [
    "Paper", "ReviewReport", "DimensionReview", "MetaReview",
    "VerificationResult", "Recommendation",
]
__version__ = "0.1.0"
