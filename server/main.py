import pathlib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Load .env from project root BEFORE importing modules that read env
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

from security import verify_secret
from generator import materialize_app
from github_ops import (
    ensure_repo, write_license_and_readme, add_pages_workflow,
    git_push_and_get_commit, pages_url, repo_url
)
from notifier import post_with_backoff

APP = FastAPI(title="LLM Build & Deploy")

class Attachment(BaseModel):
    name: str
    url: str

class TaskRequest(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: list[str] = Field(default_factory=list)
    evaluation_url: str
    attachments: list[Attachment] = Field(default_factory=list)

@APP.post("/task")
async def accept_task(req: TaskRequest):
    if not verify_secret(req.secret):
        raise HTTPException(status_code=401, detail="Invalid secret")

    repo_name = req.task.replace("/", "-")
    work_dir = str(pathlib.Path(__file__).resolve().parents[1] / "app" / repo_name)

    await materialize_app(work_dir, req.brief, [a.model_dump() for a in req.attachments])
    # Build a title and summary for README/license
title = (repo_name or req.task).replace("-", " ").replace("_", " ").title() # type: ignore
summary = (
    f"{req.brief}\n\n"
    f"This app was generated automatically for task '{req.task}' (round {req.round})."
)

write_license_and_readme(work_dir, title, summary)
    add_pages_workflow(work_dir)

    ensure_repo(repo_name, work_dir)
    commit_sha = git_push_and_get_commit(work_dir, repo_name)

    payload = {
        "email": req.email, "task": req.task, "round": req.round, "nonce": req.nonce,
        "repo_url": repo_url(repo_name), "commit_sha": commit_sha, "pages_url": pages_url(repo_name),
    }
    ok, msg = await post_with_backoff(req.evaluation_url, payload)
    return {"status": "ok" if ok else "accepted", **payload, **({"note": msg} if not ok else {})}
@APP.get("/")
def root():
    return {"status": "ok", "hint": "POST /task with JSON to build & deploy"}

@APP.get("/healthz")
def health():
    return {"ok": True}

@APP.get("/favicon.ico")
def favicon():
    from fastapi.responses import Response
    return Response(content=b"", media_type="image/x-icon")