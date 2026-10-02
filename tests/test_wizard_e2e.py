# -*- coding: utf-8 -*-
"""The whole way a user takes: wizard in a browser, server-side run, unit.

The other end-to-end tests call the pipeline directly. This one starts the
real application against an OpenAI-compatible test server
(tests/mock_openai_server.py, backed by the mock LLM, with embeddings and a
reranker), and drives the wizard in Chromium through its visible labels:

  English interface, input written in German, unit language English,
  uploaded material, all five steps, script handout; then, in a new browser
  session, loading the job with its pickup code and deleting it.

It checks what only this path shows: that the chosen unit language survives
the model's learner profile, that the embedder works without an API key,
that the production log is readable, and that the delivered unit is in the
chosen language, works offline and makes no network request.

Needs gradio, playwright and Chromium (python -m playwright install
chromium); skipped without them.
"""
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tests._optional import installed  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(url: str, seconds: int = 90) -> bool:
    import urllib.request
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001 — not up yet
            time.sleep(1)
    return False


def check(ok: bool, name: str) -> int:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    return 0 if ok else 1


def run() -> int:
    if not (installed("gradio") and installed("playwright")):
        print("  ---  gradio or playwright not installed, skipped")
        return 0
    from playwright.sync_api import sync_playwright
    from src.i18n import tr

    def L(text):
        return tr(text, "en")

    work = Path(tempfile.mkdtemp(prefix="lw-e2e-"))
    llm_port, app_port = _free_port(), _free_port()
    base = f"http://127.0.0.1:{llm_port}"
    env = {**os.environ, "LLM1_BASE_URL": f"{base}/v1", "LLM1_MODEL": "mock-strong",
           "LLM1_API_KEY": "", "LLM1_FAMILY": "generic",
           "LLM2_BASE_URL": f"{base}/v1", "LLM2_MODEL": "mock-fast",
           "EMBEDDER_BASE_URL": f"{base}/v1", "EMBEDDER_MODEL": "mock-embed", "EMBEDDER_API_KEY": "",
           "RERANKER_BASE_URL": f"{base}/rerank", "RERANKER_API_KEY": "",
           "APP_ROOT_PATH": "/lernwerkstatt", "GRADIO_SERVER_PORT": str(app_port),
           "GRADIO_SERVER_NAME": "127.0.0.1", "WORK_DIR": str(work / "work"), "APP_LANGUAGE": ""}
    material = work / "material.md"
    material.write_text("# Kubernetes\n\n## Desired State\nKubernetes gleicht den gewünschten "
                        "mit dem tatsächlichen Zustand ab.\n", encoding="utf-8")
    server = subprocess.Popen([sys.executable, str(REPO / "tests" / "mock_openai_server.py"),
                               str(llm_port)], cwd=REPO, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    app_log = work / "app.log"
    with open(app_log, "w") as log:
        app = subprocess.Popen([sys.executable, "app.py"], cwd=REPO, env=env,
                               stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{app_port}/lernwerkstatt/"
    f = 0
    try:
        if not _wait(url):
            return check(False, "application started") + 0
        startup = app_log.read_text(encoding="utf-8")
        f += check("[startup] embedder: operational" in startup,
                   "embedder operational without an API key")
        f += check("[startup] reranker: operational" in startup,
                   "reranker operational without an API key")
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as e:  # noqa: BLE001
                print(f"  ---  Chromium not available ({str(e)[:60]}), skipped")
                return f
            page = browser.new_context(locale="en-US").new_page()
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.goto(url)
            page.wait_for_selector("textarea", timeout=60000)

            # Step 1: German input, English unit, uploaded material
            page.get_by_label(L("Where do you stand? (prior knowledge — one sentence or a full "
                                "competence profile)")).fill("Ich kenne Docker gut.")
            page.get_by_label(L("What do you want to learn? (goal or knowledge gap)")).fill(
                "Kubernetes verstehen")
            dd = page.get_by_label(L("Language of the unit"))
            dd.click()
            dd.fill("English")
            page.get_by_role("option", name="English").click()
            page.locator("input[type=file]").first.set_input_files(str(material))
            page.wait_for_timeout(1500)
            page.get_by_role("button", name=L("Next →"), exact=True).click()

            # Step 2 (if there are questions) and the checkpoint
            h2 = L("## 2 · Briefing")[3:]
            h3 = L("## 3 · Plan review — the checkpoint")[3:]
            page.wait_for_function(
                "([a,b]) => [...document.querySelectorAll('h2')].some(h => h.offsetParent "
                "&& (h.innerText.includes(a) || h.innerText.includes(b)))", arg=[h2, h3], timeout=120000)
            code = re.search(r"\b[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}\b", page.inner_text("body"))
            f += check(bool(code), "pickup code shown")
            if page.get_by_text(h2).first.is_visible():
                page.get_by_label(L("Your answers (free text)")).fill("Hands-on.")
                page.get_by_role("button", name=L("On to the gap analysis →")).click()
                page.get_by_text(h3).first.wait_for(state="visible", timeout=120000)
            page.get_by_role("button", name=L("✓ Approve and start production")).click()

            # Steps 4 and 5
            page.get_by_text(L("## 5 · Result")[3:]).first.wait_for(state="visible", timeout=240000)
            page.wait_for_timeout(2000)
            body = page.inner_text("body")
            f += check("[layer_start]" not in body and "[task_done]" not in body,
                       "production log shows readable lines, not raw events")
            links = [a.get_attribute("href") for a in page.locator("a[href*='/file=']").all()]
            html_link = next((x for x in links if x.endswith(".html")), None)
            f += check(bool(html_link), "the unit is offered for download")
            page.get_by_role("button", name=L("Create script handout (MD + Word)")).click()
            page.wait_for_timeout(6000)
            hrefs = [a.get_attribute("href") for a in page.locator("a[href*='/file=']").all()]
            f += check(any(h.endswith(".md") for h in hrefs) and any(h.endswith(".docx") for h in hrefs),
                       "script handout as Markdown and Word")
            f += check(not page_errors, "no script errors in the interface")

            # The delivered unit, opened as a learner would, offline
            unit_file = work / "unit.html"
            unit_file.write_bytes(page.request.get(
                html_link if html_link.startswith("http") else f"http://127.0.0.1:{app_port}{html_link}").body())
            up = browser.new_context().new_page()
            unit_errors, requests = [], []
            up.on("pageerror", lambda e: unit_errors.append(str(e)))
            up.on("request", lambda r: requests.append(r.url)
                  if not r.url.startswith(("file:", "data:", "blob:", "about:")) else None)
            up.goto(unit_file.as_uri())
            up.wait_for_timeout(2000)
            f += check(up.evaluate("document.documentElement.lang") == "en",
                       "unit in the chosen language although the input was German")
            f += check(up.evaluate("document.getElementById('navToggle').textContent") == "☰ Contents"
                       and up.evaluate("document.getElementById('path').getAttribute('aria-label')")
                       == "Learning path", "unit controls and accessibility labels in English")
            for a in up.locator("nav a").all()[1:3]:
                a.click()
                up.wait_for_timeout(500)
            f += check(not unit_errors, "no script errors in the unit")
            f += check(not requests, "the unit makes no network request")

            # Load and delete with the pickup code, in a new session
            if code:
                page = browser.new_context(locale="en-US").new_page()
                page.goto(url)
                page.wait_for_selector("textarea", timeout=60000)
                page.get_by_text(L("Continue or delete a job")).first.click()
                page.get_by_label(L("Pickup code")).fill(code.group(0))
                page.get_by_role("button", name=L("Load job")).click()
                try:
                    page.get_by_text(L("## 5 · Result")[3:]).first.wait_for(state="visible", timeout=60000)
                    loaded = True
                except Exception:  # noqa: BLE001
                    loaded = False
                f += check(loaded, "job loads with its pickup code in a new session")
                page.goto(url)
                page.wait_for_selector("textarea", timeout=60000)
                page.get_by_text(L("Continue or delete a job")).first.click()
                page.get_by_label(L("Pickup code")).fill(code.group(0))
                page.get_by_label(L("Delete the job with all its files for good (material, "
                                    "intermediate results, result)")).check()
                page.get_by_role("button", name=L("Delete job")).click()
                page.wait_for_timeout(3000)
                f += check(not any((work / "work").glob("job-*")), "deleting removes the job folder")
            browser.close()
        return f
    finally:
        app.terminate()
        server.terminate()
        for proc in (app, server):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_wizard_e2e():
    assert run() == 0


if __name__ == "__main__":
    print("wizard end to end in a browser")
    errors = run()
    print(f"\n{'WIZARD E2E OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
