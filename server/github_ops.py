import os
import subprocess
from pathlib import Path
import httpx

GITHUB_USER = os.environ["GITHUB_USER"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

def sh(cmd: str, cwd: str | None = None) -> str:
    res = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{res.stdout}\n{res.stderr}")
    return res.stdout.strip()

def _create_repo_via_api(repo_name: str) -> None:
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    payload = {"name": repo_name, "private": False, "auto_init": False}
    r = httpx.post("https://api.github.com/user/repos", headers=headers, json=payload)
    # 201 = created, 422 = already exists
    if r.status_code not in (201, 422):
        raise RuntimeError(f"GitHub repo create failed ({r.status_code}): {r.text}")

def ensure_repo(repo_name: str, work_dir: str) -> None:
    """Create repo via API and push initial commit."""
    _create_repo_via_api(repo_name)

    sh("git init -b main", cwd=work_dir)
    sh(f'git config user.name "{GITHUB_USER}"', cwd=work_dir)
    sh(f'git config user.email "{GITHUB_USER}@users.noreply.github.com"', cwd=work_dir)

    remote_url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{repo_name}.git"
    try:
        sh("git remote remove origin", cwd=work_dir)
    except Exception:
        pass
    sh(f'git remote add origin "{remote_url}"', cwd=work_dir)

def write_license_and_readme(work_dir: str, title: str, summary: str) -> None:
    Path(work_dir, "LICENSE").write_text(
        "MIT License\n\nCopyright (c) 2025\n\nPermission is hereby granted, free of charge, "
        "to any person obtaining a copy of this software and associated documentation files "
        "(the 'Software'), to deal in the Software without restriction, including without "
        "limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, "
        "and/or sell copies of the Software.\n", encoding="utf-8"
    )

    Path(work_dir, "README.md").write_text(
        f"# {title}\n\n{summary}\n\n## License\nMIT\n", encoding="utf-8"
    )

def add_pages_workflow(work_dir: str) -> None:
    wf_dir = Path(work_dir, ".github", "workflows")
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf = wf_dir / "pages.yml"
    wf.write_text(
        """name: Deploy to GitHub Pages
on:
  push:
    branches: [ "main" ]
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .
  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
""",
        encoding="utf-8",
    )

def git_push_and_get_commit(work_dir: str) -> str:
    sh("git add .", cwd=work_dir)
    sh('git commit -m "auto: build" --allow-empty', cwd=work_dir)
    sh("git branch -M main", cwd=work_dir)
    sh("git push -u origin main", cwd=work_dir)
    return sh("git rev-parse HEAD", cwd=work_dir)

def repo_url(repo_name: str) -> str:
    return f"https://github.com/{GITHUB_USER}/{repo_name}"

def pages_url(repo_name: str) -> str:
    return f"https://{GITHUB_USER}.github.io/{repo_name}/"