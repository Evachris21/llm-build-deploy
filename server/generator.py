import os, pathlib, json, httpx

LLM_BASE  = os.getenv("LLM_API_BASE")
LLM_KEY   = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

SYSTEM = """You write minimal static web apps. Return JSON: {"files":[{"path","content"}]}.
Must: read ?url= for an image, show it, run Tesseract.js OCR, print text within 15s, responsive UI."""
USER_TPL = """Brief: {brief}
Files: index.html, styles.css (optional)"""

async def call_llm(brief: str):
    # If no creds, just skip to fallback.
    if not (LLM_BASE and LLM_KEY):
        return {}
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TPL.format(brief=brief)}
        ],
        "temperature": 0.3
    }
    headers = {"Authorization": f"Bearer {LLM_KEY}"}
    try:
        async with httpx.AsyncClient(base_url=LLM_BASE, headers=headers, timeout=60) as client:
            r = await client.post("/chat/completions", json=payload)
            # Do NOT raise; treat non-200 as "no LLM output".
            if r.status_code != 200:
                print("LLM call non-200:", r.status_code, r.text)
                return {}
            data = r.json()
            try:
                return json.loads(data["choices"][0]["message"]["content"])
            except Exception:
                return {}
    except Exception as e:
        # Any network/auth error -> return {} so we fall back.
        print("LLM call failed:", e)
        return {}

def builtin_template(default_url: str):
    html = """<!doctype html>
<html lang="en"><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Captcha Solver</title>
<link rel="stylesheet" href="styles.css"/>
<body><main>
<h1>Captcha Solver</h1>
<p>Pass image via <code>?url=</code>. If absent, a sample is used.</p>
<img id="img" alt="captcha"/>
<pre id="result">Solving…</pre>
</main>
<script src="https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js"></script>
<script>
const q=new URLSearchParams(location.search);
const url=q.get('url')||"{DEFAULT_URL}";
document.getElementById('img').src=url;
Tesseract.recognize(url,'eng',{logger:m=>console.log(m)}).then(({data})=>{
  document.getElementById('result').textContent=(data.text||'').trim()||'(no text found)';
}).catch(e=>{document.getElementById('result').textContent='Error: '+e});
</script></body></html>"""
    css = "body{font-family:system-ui;margin:16px}main{max-width:720px;margin:auto}img{max-width:100%;border:1px solid #ddd;border-radius:8px}pre{background:#111;color:#0f0;padding:12px;border-radius:8px}"
    return [
        {"path": "index.html", "content": html.replace("{DEFAULT_URL}", default_url or "")},
        {"path": "styles.css", "content": css}
    ]

PAGES_YML = """name: Deploy to GitHub Pages
on:
  push:
    branches: ["main"]
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: "pages"
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: .
  deploy:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
"""

async def materialize_app(local_dir: str, brief: str, attachments: list):
    # Ensure working directory exists
    pathlib.Path(local_dir).mkdir(parents=True, exist_ok=True)

    # Provide default attachment URL (if any)
    default_url = attachments[0].get("url", "") if attachments else ""

    # Ask LLM for files, or fall back to a built-in template
    llm = await call_llm(brief)
    files = llm.get("files") if llm else None
    if not files:
        files = builtin_template(default_url)

    # Write all returned files
    for f in files:
        p = pathlib.Path(local_dir) / f["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f["content"], encoding="utf-8")

    # 👉 Write the GitHub Pages workflow (this is the missing step)
    workflow_dir = pathlib.Path(local_dir) / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "pages.yml").write_text(PAGES_YML, encoding="utf-8")
