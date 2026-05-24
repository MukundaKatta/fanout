"""Eva operator — one autonomous draft-generation cycle.

The operator is a thin wrapper around the existing /generate pipeline that
adds two things:

1.  An **autonomous experiment picker** that biases snippet selection toward
    sources whose past drafts have produced engagement (via the outcome
    leaderboard).  Cold-start falls back to plain score-desc.
2.  An **OperatorRun audit row** for every cycle so we can replay what was
    picked and how it performed later.

Kept separate from ``main.py`` so the endpoint stays narrow and the operator
logic is testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import store
from app.agent import PLATFORMS, SocialAgent
from app.research import Snippet, format_for_prompt


@dataclass
class OperatorResult:
    run_id: str
    plan: dict
    drafts: list[dict]
    picked_snippets: list[dict]
    leaderboard_used: bool
    winning_sources: list[dict]


def run(
    user_id: str,
    *,
    product: str,
    platforms: list[str] | None = None,
    weight_by_leaderboard: bool = True,
    leaderboard_metric: str = "likes",
    snippet_limit: int = 8,
    agent: SocialAgent | None = None,
) -> OperatorResult:
    """Drive one operator cycle end-to-end.

    The ``agent`` parameter is the seam tests use to inject a stubbed agent
    so we never hit Groq.  Production paths leave it unset and build a real
    SocialAgent on demand.

    Raises whatever the agent raises if the underlying call fails, but
    always closes out the OperatorRun row (``failed`` on exception, ``ok``
    on success) so the audit trail never leaks ``pending`` rows.
    """
    platforms = platforms or list(PLATFORMS)
    invalid = [p for p in platforms if p not in PLATFORMS]
    if invalid:
        raise ValueError(f"Invalid platforms: {invalid}")

    run_row = store.start_operator_run(
        user_id,
        product=product,
        platforms=platforms,
        weight_by_leaderboard=weight_by_leaderboard,
        leaderboard_metric=leaderboard_metric,
    )
    run_id = run_row["id"]

    try:
        pick = store.select_experiment_snippets(
            user_id,
            limit=snippet_limit,
            weight_by_leaderboard=weight_by_leaderboard,
            leaderboard_metric=leaderboard_metric,
        )
        snippets = pick["snippets"]
        snippet_ids = [s["id"] for s in snippets]
        research_block = None
        if snippets:
            objs = [
                Snippet(
                    source=s["source"],
                    url=s["url"],
                    title=s["title"],
                    snippet=s.get("snippet"),
                    score=s.get("score") or 0.0,
                )
                for s in snippets
            ]
            research_block = format_for_prompt(objs)

        agent = agent or SocialAgent()
        result = agent.run(product, platforms=tuple(platforms), research_context=research_block)
        drafts = store.save_drafts(user_id, product, result, cited_snippet_ids=snippet_ids)
        if snippet_ids and drafts:
            store.mark_snippets_used(user_id, snippet_ids, drafts[0]["id"])

        notes = _build_notes(pick, drafts_count=len(drafts))
        store.complete_operator_run(
            user_id,
            run_id,
            cited_snippet_ids=snippet_ids,
            draft_ids=[d["id"] for d in drafts],
            notes=notes,
        )
        return OperatorResult(
            run_id=run_id,
            plan=result.get("plan", {}),
            drafts=drafts,
            picked_snippets=snippets,
            leaderboard_used=pick["leaderboard_used"],
            winning_sources=pick["winning_sources"],
        )
    except Exception as exc:  # noqa: BLE001 — capture, log, re-raise
        store.fail_operator_run(user_id, run_id, error=f"{type(exc).__name__}: {exc}")
        raise


def _build_notes(pick: dict, *, drafts_count: int) -> str:
    if pick["leaderboard_used"]:
        winners = ", ".join(
            f"{w['source']}/{w['query'] or '*'}" for w in pick["winning_sources"][:5]
        )
        return (
            f"leaderboard-weighted; {len(pick['snippets'])} snippets fed "
            f"{drafts_count} drafts. winners: {winners}"
        )
    if not pick["snippets"]:
        return f"cold-start (no banked snippets); {drafts_count} drafts produced ungrounded"
    return f"cold-start (no leaderboard yet); {len(pick['snippets'])} top-score snippets fed {drafts_count} drafts"
