from fastapi import HTTPException
import pathlib

@APP.post("/task")
async def accept_task(req: TaskRequest):
    # 1) Secret check
    if not verify_secret(req.secret):
        raise HTTPException(status_code=401, detail="Invalid secret")

    # 2) Derive repo/work directory
    repo_name = req.task.replace("/", "-")
    work_dir = str(pathlib.Path(__file__).resolve().parents[1] / "app" / repo_name)

    # 3) Generate the app contents
    await materialize_app(
        work_dir,
        req.brief,
        [a.model_dump() for a in req.attachments],
    )

    # 4) README + LICENSE content (title + summary)
    title = (repo_name or req.task).replace("-", " ").replace("_", " ").title()
    summary = (
        f"{req.brief}\n\n"
        f"This app was generated automatically for task '{req.task}' (round {req.round})."
    )
    write_license_and_readme(work_dir, title, summary)

    # 5) GitHub Pages workflow
    add_pages_workflow(work_dir)

    # 6) Create repo (via API) and push
    ensure_repo(repo_name, work_dir)
    commit_sha = git_push_and_get_commit(work_dir)

    # 7) Notify evaluation endpoint
    payload = {
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
