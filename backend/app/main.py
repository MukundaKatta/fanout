"""Fanout backend — FastAPI."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend root regardless of cwd.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import Depends, FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app import store  # noqa: E402
from app.agent import PLATFORMS, SocialAgent  # noqa: E402
from app.auth import current_user  # noqa: E402
from app.db import init_db  # noqa: E402
from app.research import ResearchRequest, format_for_prompt, run_research  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Fanout API", version="0.3.0", lifespan=lifespan)

origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    product: str = Field(..., min_length=10, max_length=8000)
    platforms: list[str] = Field(default_factory=lambda: list(PLATFORMS))
    # When true, the agent prepends the user's top unused research snippets
    # to its plan/write prompts so drafts can reference live conversation.
    use_research: bool = False


class VariationsRequest(BaseModel):
    product: str = Field(..., min_length=10, max_length=8000)
    platform: str
    count: int = Field(default=5, ge=1, le=8)
    use_research: bool = False


class ResearchRunRequest(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=10)
    rss_feeds: list[str] = Field(default_factory=list, max_length=10)
    sources: list[str] = Field(default_factory=lambda: ["hn", "devto", "reddit", "rss"])
    per_source_limit: int = Field(default=10, ge=1, le=25)


class ScheduleRequest(BaseModel):
    scheduled_at: datetime


class PostedReport(BaseModel):
    draft_id: str
    post_url: str | None = None
    error: str | None = None


class BulkQueueRequest(BaseModel):
    draft_ids: list[str]


class ReviewCheckpointRequest(BaseModel):
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: str | None = None


class ReviewApprovalRequest(BaseModel):
    reviewer: str = Field(..., min_length=2, max_length=120)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/me")
def me(uid: str = Depends(current_user)):
    return {"user_id": uid}


def _build_research_context(uid: str, *, enabled: bool) -> tuple[str | None, list[str]]:
    """Return (prompt block, snippet ids) — empty when disabled or no banked snippets."""
    if not enabled:
        return None, []
    snippets = store.top_snippets_for_agent(uid, limit=8)
    if not snippets:
        return None, []
    # Re-render via ``format_for_prompt`` so we share the truncation/formatting
    # logic with anything else that wants to feed snippets into a prompt.
    from app.research import Snippet  # local import to keep the module boundary clean

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
    return format_for_prompt(objs), [s["id"] for s in snippets]


@app.post("/generate")
def generate(req: GenerateRequest, uid: str = Depends(current_user)):
    invalid = [p for p in req.platforms if p not in PLATFORMS]
    if invalid:
        raise HTTPException(400, f"Invalid platforms: {invalid}. Valid: {PLATFORMS}")
    research_block, snippet_ids = _build_research_context(uid, enabled=req.use_research)
    agent = SocialAgent()
    result = agent.run(req.product, platforms=tuple(req.platforms), research_context=research_block)
    drafts = store.save_drafts(uid, req.product, result)
    # Mark every consumed snippet against the *first* draft — keeps the
    # used/unused signal accurate without needing per-platform attribution.
    if snippet_ids and drafts:
        store.mark_snippets_used(uid, snippet_ids, drafts[0]["id"])
    return {"plan": result["plan"], "drafts": drafts, "research_used": len(snippet_ids)}


@app.post("/variations")
def variations(req: VariationsRequest, uid: str = Depends(current_user)):
    if req.platform not in PLATFORMS:
        raise HTTPException(400, f"Invalid platform. Valid: {PLATFORMS}")
    research_block, snippet_ids = _build_research_context(uid, enabled=req.use_research)
    agent = SocialAgent()
    items = agent.variations(req.product, req.platform, n=req.count, research_context=research_block)
    drafts = store.save_variations(uid, req.product, req.platform, items)
    if snippet_ids and drafts:
        store.mark_snippets_used(uid, snippet_ids, drafts[0]["id"])
    return {"drafts": drafts, "research_used": len(snippet_ids)}


# --- research ---------------------------------------------------------------


@app.post("/research")
def research_run(req: ResearchRunRequest, uid: str = Depends(current_user)):
    if not req.queries and not req.rss_feeds:
        raise HTTPException(400, "Provide at least one query or RSS feed.")
    snippets = run_research(
        ResearchRequest(
            queries=req.queries,
            rss_feeds=req.rss_feeds,
            sources=req.sources,
            per_source_limit=req.per_source_limit,
        )
    )
    saved = store.upsert_snippets(uid, snippets)
    return {"fetched": len(snippets), "saved": saved}


@app.get("/research")
def research_list(
    source: str | None = None,
    only_unused: bool = False,
    limit: int = 50,
    uid: str = Depends(current_user),
):
    return store.list_snippets(uid, source=source, only_unused=only_unused, limit=limit)


@app.post("/queue-bulk")
def queue_bulk(req: BulkQueueRequest, uid: str = Depends(current_user)):
    queued = []
    for did in req.draft_ids:
        d = store.queue_now(uid, did)
        if d:
            queued.append(d)
    return {"queued": queued}


@app.get("/drafts")
def list_drafts(status: str | None = None, uid: str = Depends(current_user)):
    return store.list_drafts(uid, status=status)


@app.get("/drafts/{draft_id}")
def get_draft(draft_id: str, uid: str = Depends(current_user)):
    d = store.get_draft(uid, draft_id)
    if not d:
        raise HTTPException(404, "Not found")
    return d


@app.get("/platforms/{platform}/adapter")
def adapter_contract(platform: str, uid: str = Depends(current_user)):
    adapter = store.channel_adapter_contract(platform)
    if not adapter:
        raise HTTPException(404, "Platform not found")
    return {"user_id": uid, "adapter": adapter}


@app.patch("/drafts/{draft_id}")
def update_draft(draft_id: str, content: str, uid: str = Depends(current_user)):
    d = store.update_content(uid, draft_id, content)
    if not d:
        raise HTTPException(404, "Not found")
    return d


@app.post("/drafts/{draft_id}/queue")
def queue(draft_id: str, uid: str = Depends(current_user)):
    d = store.queue_now(uid, draft_id)
    if not d:
        raise HTTPException(404, "Not found")
    return d


@app.post("/drafts/{draft_id}/review-checkpoint")
def review_checkpoint(draft_id: str, req: ReviewCheckpointRequest, uid: str = Depends(current_user)):
    d = store.set_review_checkpoint(uid, draft_id, req.confidence, req.notes)
    if not d:
        raise HTTPException(404, "Not found")
    checkpoint = store.build_review_checkpoint(d, req.confidence)
    return {"draft": d, "checkpoint": checkpoint}


@app.post("/drafts/{draft_id}/approve")
def approve_review(draft_id: str, req: ReviewApprovalRequest, uid: str = Depends(current_user)):
    d = store.approve_review(uid, draft_id, req.reviewer)
    if not d:
        raise HTTPException(404, "Not found")
    return d


@app.post("/drafts/{draft_id}/schedule")
def schedule(draft_id: str, req: ScheduleRequest, uid: str = Depends(current_user)):
    d = store.schedule(uid, draft_id, req.scheduled_at)
    if not d:
        raise HTTPException(404, "Not found")
    return d


@app.delete("/drafts/{draft_id}/schedule")
def cancel_schedule(draft_id: str, uid: str = Depends(current_user)):
    d = store.cancel_schedule(uid, draft_id)
    if not d:
        raise HTTPException(404, "Not found")
    return d


@app.get("/queue")
def get_queue(platform: str | None = None, uid: str = Depends(current_user)):
    return store.due_for_posting(uid, platform=platform)


@app.post("/posted")
def report_posted(report: PostedReport, uid: str = Depends(current_user)):
    if report.error:
        d = store.mark_failed(uid, report.draft_id, report.error)
    else:
        d = store.mark_posted(uid, report.draft_id, report.post_url)
    if not d:
        raise HTTPException(404, "Not found")
    return d
