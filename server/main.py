# server/main.py

from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from security import verify_secret
from generator import materialize_app
from github_ops import (
    ensure_repo,
    write_license_and_readme,
    add_pages_workflow,
    git_push_and_get_commit,
    pages_url,
    repo_url,
)
from notifier import post_with_backoff


# ---------------------------------------------------------------------
# Load .env and create FastAPI app BEFORE any route decorators
# ---------------------------------------------------------------------
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
APP = FastAPI(title="LLM Build & Deploy")


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------
class Attachment(BaseModel):
    name: str
    url: str


class TaskRequest(BaseModel):
    email: str
    secret: str
    task: str
    round: int = Field(ge=1)
    nonce: str
    brief: str
    checks: List[str] = []
    evaluation_url: str
    attachments: List[Attachment] = []


# ---------------------------------------------------------------------
# Health & info
# ---------------------------------------------------------------------
@APP.get("/")
def root():
    return {
        "status": "ok",
        "message": "LLM Build & Deploy API. POST /task with the JSON request to trigger a build.",
        "docs": "/docs",
    }


# ---------------------------------------------------------------------
# Main task endpoint
# ---------------------------------------------------------------------
@APP.post("/task")
async def accept_task(req: TaskRequest):
    # 1️⃣ Secret check
    if not verify_secret(req.secret):
        raise HTTPException(status_code=401, detail="Invalid secret")

    # 2️⃣ Derive repo/work directory
    repo_name = req.task.replace("/", "-")
    work_dir = str(Path(__file__).resolve().parents[1] / "app" / repo_name)

    # 3️⃣ Ensure repo exists and is synced before writing files
    ensure_repo(repo_name, work_dir)

    # 4️⃣ Generate the app contents
    await materialize_app(
        work_dir,
        req.brief,
        [a.model_dump() for a in req.attachments],
    )

    # 5️⃣ README + LICENSE
    title = (repo_name or req.task).replace("-", " ").replace("_", " ").title()
    summary = (
        f"{req.brief}\n\n"
        f"This app was generated automatically for task '{req.task}' (round {req.round})."
    )
    write_license_and_readme(work_dir, title, summary)

    # 6️⃣ GitHub Pages workflow
    add_pages_workflow(work_dir)

    # 7️⃣ Commit and push
    commit_sha = git_push_and_get_commit(work_dir)

    # ✅ Return JSON
    return {
        "status": "ok",
        "email": req.email,
        "task": req.task,
        "round": req.round,
        "nonce": req.nonce,
        "repo_url": repo_url(repo_name),
        "commit_sha": commit_sha,
        "pages_url": pages_url(repo_name),
    }
    ok, msg = await post_with_backoff(req.evaluation_url, payload)

    # 8) Response back to caller
    return {
        "status": "ok" if ok else "accepted",
        **payload,
        **({"note": msg} if not ok else {}),
    }
