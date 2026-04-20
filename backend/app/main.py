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


class VariationsRequest(BaseModel):
    product: str = Field(..., min_length=10, max_length=8000)
    platform: str
    count: int = Field(default=5, ge=1, le=8)


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


@app.post("/generate")
def generate(req: GenerateRequest, uid: str = Depends(current_user)):
    invalid = [p for p in req.platforms if p not in PLATFORMS]
    if invalid:
        raise HTTPException(400, f"Invalid platforms: {invalid}. Valid: {PLATFORMS}")
    agent = SocialAgent()
    result = agent.run(req.product, platforms=tuple(req.platforms))
    drafts = store.save_drafts(uid, req.product, result)
    return {"plan": result["plan"], "drafts": drafts}


@app.post("/variations")
def variations(req: VariationsRequest, uid: str = Depends(current_user)):
    if req.platform not in PLATFORMS:
        raise HTTPException(400, f"Invalid platform. Valid: {PLATFORMS}")
    agent = SocialAgent()
    items = agent.variations(req.product, req.platform, n=req.count)
    drafts = store.save_variations(uid, req.product, req.platform, items)
    return {"drafts": drafts}


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
