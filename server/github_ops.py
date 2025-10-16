import os
import subprocess
import pathlib
import textwrap
from pathlib import Path
from dotenv import load_dotenv

# Ensure .env is loaded even if caller forgot (looks one level above /server)
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


def _get_user() -> str:
    user = os.getenv("GITHUB_USER")
    if not user:
        raise RuntimeError(
            "GITHUB_USER is not set. Check your .env and that load_dotenv ran before importing github_ops."
        )
    return user


def sh(cmd: str, cwd: str | None = None) -> str:
    """Run a shell command and raise on failure (prints stdout/stderr on error)."""
    print(">>", cmd)
    res = subprocess.run(cmd, shell=True, cwd=cwd, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{res.stdout}\n{res.stderr}")
    return res.stdout.strip()


def ensure_repo(repo_name: str, local_dir: str):
    """
    Initialize a git repo IN PLACE (do NOT delete local_dir since the app files
    were already generated there). Create a public GitHub repo if it doesn't exist.
    """
    GITHUB_USER = _get_user()

    os.makedirs(local_dir, exist_ok=True)
    # init repo and set identity
    sh("git init -b main", cwd=local_dir)
    sh(f'git config user.name "{GITHUB_USER}"', cwd=local_dir)
    sh(f'git config user.email "{GITHUB_USER}@users.noreply.github.com"', cwd=local_dir)

    # Try to create the remote repo; if it already exists, ignore that error
    try:
        # gh CLI deprecated --confirm; use -y to skip prompt
        sh(f'gh repo create {GITHUB_USER}/{repo_name} --public -y')
    except RuntimeError as e:
        # If it already exists, continue; anything else bubble up
        if "already exists" not in str(e).lower():
            raise

    # Ensure README/LICENSE/workflow will be committed later by caller


def write_license_and_readme(local_dir: str, brief: str):
    """Write an MIT LICENSE and a concise README.md that satisfies checks."""
    (pathlib.Path(local_dir) / "LICENSE").write_text(textwrap.dedent("""\
    MIT License

    Copyright (c) 2025

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in
    all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
    THE SOFTWARE.
    """))

    (pathlib.Path(local_dir) / "README.md").write_text(textwrap.dedent(f"""\
    # Auto-Built App

    **Summary:** {brief}

    ## Usage
    Open the GitHub Pages URL (see repo About). Pass `?url=` pointing to a CAPTCHA image, for example:
    `?url=https://upload.wikimedia.org/wikipedia/commons/4/4b/Example.png`

    ## Code Structure
    - `index.html` + `styles.css`: minimal OCR web app using Tesseract.js (via CDN)
    - `.github/workflows/pages.yml`: GitHub Actions workflow that deploys the site to Pages

    ## Development
    Static site; open `index.html` locally or via GitHub Pages. OCR runs in-browser.

    ## License
    MIT
    """))


def add_pages_workflow(local_dir: str):
    """Add a GitHub Actions workflow that deploys the repo as a static site to Pages."""
    wf = pathlib.Path(local_dir) / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "pages.yml").write_text("""\
name: Deploy static site to Pages
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
      - uses: actions/configure-pages@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
""")


def git_push_and_get_commit(local_dir: str, repo_name: str) -> str:
    """Commit current contents and push to origin/main. Return the commit SHA."""
    GITHUB_USER = _get_user()

    sh("git add .", cwd=local_dir)
    # --allow-empty avoids failure if generator produced nothing (still lets workflow run)
    sh('git commit -m "auto: build" --allow-empty', cwd=local_dir)

    # Add origin if missing
    try:
        sh("git remote get-url origin", cwd=local_dir)
    except RuntimeError:
        sh(f"git remote add origin https://github.com/{GITHUB_USER}/{repo_name}.git", cwd=local_dir)

    sh("git push -u origin main", cwd=local_dir)
    return sh("git rev-parse HEAD", cwd=local_dir)


def pages_url(repo_name: str) -> str:
    return f"https://{_get_user()}.github.io/{repo_name}/"


def repo_url(repo_name: str) -> str:
    return f"https://github.com/{_get_user()}/{repo_name}"