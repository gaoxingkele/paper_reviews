"""Orchestrator: drives the review pipeline for one paper against one venue.

Reads the journal profile (config/journals/<venue>.yaml) to decide which
dimension agents to run, on what rubric, with what strictness. Dimension
reviews run INDEPENDENTLY (no cross-talk) per the AgentReview reliability
finding, then are aggregated by an inclusive meta-reviewer that preserves
disagreement.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import statistics
from dataclasses import asdict

from .config import JournalProfile, load_agents_config, load_journal
from .agents.base import AgentSpec
from .agents.roles import (DeskScreener, DimensionReviewer, MetaReviewer,
                           ReviewCritic, VenueMatcher, Verifier)
from .models import (CrossJournalReport, Paper, ReviewReport, DimensionReview)
from . import scoring

logger = logging.getLogger("paper_reviews.orchestrator")


def _spec_for(role: str, cfg: dict) -> AgentSpec:
    import os
    default = cfg.get("default") or {}
    d = cfg.get(role) or default
    # a role may set its own fallbacks; otherwise inherit the global default chain
    fallbacks = d.get("fallbacks", default.get("fallbacks", []))
    provider = d.get("provider", "claude")
    extra = list(d.get("extra_providers", []))
    reasoning = bool(d.get("reasoning", False))
    # PR_FORCE_PROVIDER: pin every role to one healthy provider (e.g. when the
    # gateway only has Claude up) — avoids wasting retries on dead upstreams.
    forced = os.getenv("PR_FORCE_PROVIDER", "").strip()
    if forced:
        provider, extra, fallbacks = forced, [], []
        # the gateway's *-thinking reasoning model is intermittently dropping
        # connections; with fallbacks cleared a failure would drop the whole
        # dimension. Pin to the stable non-reasoning chain unless explicitly kept.
        if os.getenv("PR_FORCE_REASONING", "").strip() not in {"1", "true"}:
            reasoning = False
    return AgentSpec(
        provider=provider,
        reasoning=reasoning,
        temperature=float(d.get("temperature", 0.3)),
        voters=int(d.get("voters", 1)),
        extra_providers=extra,
        fallbacks=list(fallbacks),
    )


class Orchestrator:
    def __init__(self, venue: str, *, run_verification: bool = True,
                 run_critic: bool = True, parallel: int = 4):
        self.journal: JournalProfile = load_journal(venue)
        self.cfg = load_agents_config()
        self.run_verification = run_verification
        self.run_critic = run_critic
        self.parallel = parallel

    def review(self, paper: Paper) -> ReviewReport:
        rep = ReviewReport(paper_id=paper.paper_id, venue=self.journal.venue)

        # [2a] desk screen
        screener = DeskScreener("desk_screen", _spec_for("desk_screen", self.cfg))
        rep.desk_screen = screener.screen(paper, self.journal)
        rep.trace.append({"stage": "desk_screen", "result": rep.desk_screen})
        if rep.desk_screen.get("pass") is False:
            logger.info("Desk-rejected: %s", rep.desk_screen.get("reason"))
            return rep

        # [2b] venue match -> may adjust strictness
        matcher = VenueMatcher("venue_match", _spec_for("venue_match", self.cfg))
        rep.venue_match = matcher.match(paper, self.journal)
        rep.trace.append({"stage": "venue_match", "result": rep.venue_match})
        self._apply_strictness(rep.venue_match.get("suggested_strictness"))

        # [3] independent multi-dimension review (parallel, isolated)
        rep.dimension_reviews = self._run_dimension_reviews(paper)
        rep.trace.append({"stage": "dimension_review",
                          "n": len(rep.dimension_reviews)})

        # [4] adversarial verification of the riskiest claims
        if self.run_verification:
            rep.verifications = self._run_verification(paper, rep.dimension_reviews)
            rep.trace.append({"stage": "verification", "n": len(rep.verifications)})

        # [5] deterministic RRI risk scoring + priority-ranked revision plan
        rep.risk = scoring.score_journal(self.journal, rep.dimension_reviews)
        rep.revision_plan = scoring.build_revision_plan(rep.dimension_reviews, [self.journal])
        rep.trace.append({"stage": "risk", "rri": rep.risk.rri, "tier": rep.risk.tier})

        # [6] aggregate + meta-review (inclusive, preserves disagreement)
        meta = MetaReviewer("meta_review", _spec_for("meta_review", self.cfg))
        rep.meta_review = meta.aggregate(self.journal, rep.dimension_reviews,
                                         rep.verifications, risk=rep.risk)
        # safety net: force human review when dimension scores disagree a lot
        self._flag_disagreement(rep)
        rep.trace.append({"stage": "meta_review",
                          "recommendation": str(rep.meta_review.recommendation)})

        # [8] review-quality self-critique
        if self.run_critic:
            critic = ReviewCritic("review_critic", _spec_for("review_critic", self.cfg))
            review_json = json.dumps(
                [asdict(r) for r in rep.dimension_reviews], ensure_ascii=False)
            rep.quality_critique = critic.critique(paper.abstract, review_json)
            rep.trace.append({"stage": "review_critique"})

        return rep

    # ---- stages ----
    def _run_dimension_reviews(self, paper: Paper,
                               targets: list[JournalProfile] | None = None
                               ) -> list[DimensionReview]:
        dims = self.journal.enabled_dimensions
        results: list[DimensionReview] = []

        def _one(dim):
            spec = _spec_for(dim.agent or dim.key, self.cfg)
            reviewer = DimensionReviewer(f"reviewer:{dim.key}", spec)
            return reviewer.review(paper, self.journal, dim, targets=targets)

        with cf.ThreadPoolExecutor(max_workers=self.parallel) as ex:
            futs = {ex.submit(_one, d): d for d in dims}
            for fut in cf.as_completed(futs):
                d = futs[fut]
                try:
                    results.append(fut.result())
                except Exception as e:  # noqa: BLE001
                    logger.warning("dimension %s failed: %s", d.key, e)
        # stable order by rubric
        order = {d.key: i for i, d in enumerate(dims)}
        results.sort(key=lambda r: order.get(r.dimension, 99))
        return results

    def _run_verification(self, paper, reviews) -> list:
        verifier = Verifier("verifier", _spec_for("verifier", self.cfg))
        out = []
        context = paper.as_review_input(max_chars=30_000)
        for r in reviews:
            # verify the single most severe weakness per dimension
            if r.weaknesses:
                claim = r.weaknesses[0]
                try:
                    out.append(verifier.verify(r.dimension, claim, context))
                except Exception as e:  # noqa: BLE001
                    logger.warning("verify %s failed: %s", r.dimension, e)
        return out

    def _apply_strictness(self, suggested):
        try:
            s = float(suggested)
        except (TypeError, ValueError):
            return
        for d in self.journal.dimensions:
            d.strictness = round(d.strictness * s, 2)

    def _flag_disagreement(self, rep: ReviewReport, threshold: float = 0.30):
        norm = []
        for r in rep.dimension_reviews:
            if r.score is not None and r.scale_max:
                norm.append(r.score / r.scale_max)
        if len(norm) >= 2:
            spread = statistics.pstdev(norm)
            if rep.meta_review:
                if rep.meta_review.disagreement is None:
                    rep.meta_review.disagreement = round(spread, 3)
                if spread >= threshold:
                    rep.meta_review.needs_human_review = True


class CrossJournalOrchestrator:
    """Score ONE paper against several journals from a single set of findings.

    Per review_simulator methodology §7: dimension reviews run once (journal-aware,
    each finding carries journal_sensitivity), then RRI is computed per journal from
    the same findings using each journal's weight vector + hard-gate rules. This is
    far cheaper than re-reviewing per journal and yields a comparable risk matrix.
    """

    def __init__(self, venues: list[str], *, run_verification: bool = True,
                 run_critic: bool = False, parallel: int = 4):
        if not venues:
            raise ValueError("need at least one venue")
        self.venues = venues
        self.journals = [load_journal(v) for v in venues]
        self.primary = self.journals[0]
        self.cfg = load_agents_config()
        self.run_verification = run_verification
        self.run_critic = run_critic
        self.parallel = parallel

    def review(self, paper: Paper) -> CrossJournalReport:
        # one orchestrator drives the shared per-dimension stage against the primary
        base = Orchestrator(self.primary.venue, run_verification=self.run_verification,
                            run_critic=False, parallel=self.parallel)

        # desk screen (against primary venue scope)
        desk = DeskScreener("desk_screen", _spec_for("desk_screen", self.cfg))
        desk_res = desk.screen(paper, self.primary)

        # [3] independent multi-dimension review ONCE, aware of all target journals
        reviews = base._run_dimension_reviews(paper, targets=self.journals)

        # [4] adversarial verification once
        verifs = base._run_verification(paper, reviews) if self.run_verification else []

        # [5] deterministic cross-journal risk matrix + unified revision plan
        cj = scoring.score_cross_journal(paper.paper_id, reviews, verifs, self.journals)
        cj.desk_screen = desk_res

        # [6] per-journal meta narrative, each fed its own computed RiskScore
        meta = MetaReviewer("meta_review", _spec_for("meta_review", self.cfg))
        risk_by_venue = {r.venue: r for r in cj.risks}
        for j in self.journals:
            cj.meta_reviews[j.venue] = meta.aggregate(
                j, reviews, verifs, risk=risk_by_venue.get(j.venue))

        # [8] optional one-shot review-quality critique
        if self.run_critic:
            import json
            from dataclasses import asdict
            critic = ReviewCritic("review_critic", _spec_for("review_critic", self.cfg))
            review_json = json.dumps([asdict(r) for r in reviews], ensure_ascii=False)
            cj.quality_critique = critic.critique(paper.abstract, review_json)

        cj.trace.append({"stage": "cross_journal",
                         "rri": {r.venue: r.rri for r in cj.risks},
                         "recommended": cj.recommended_venue})
        return cj


def review_paper(venue: str, paper: Paper, **kw) -> ReviewReport:
    return Orchestrator(venue, **kw).review(paper)


def review_cross_journal(venues: list[str], paper: Paper, **kw) -> CrossJournalReport:
    return CrossJournalOrchestrator(venues, **kw).review(paper)
