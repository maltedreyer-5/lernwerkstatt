# -*- coding: utf-8 -*-
"""The generated unit in a real browser (Chromium via Playwright).

Checks what only a browser can show: the simulator computes the same values
as the model function, simulator code cannot reach the page it is embedded
in, error messages appear instead of blank output, and links keep working
inside the wizard's preview frame. Needs the playwright package and its
Chromium (`python -m playwright install chromium`); skipped without them.
"""
import copy
import html
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _optional import installed  # noqa: E402

EXAMPLE = REPO / "examples" / "example-unit.json"
LESSON = "Zinssatz und Zeit im Zusammenspiel"   # lesson with the simulator
# Deliberately on the legacy field names (serien, werte): the shell must still
# accept them, so this case also covers that fallback.
HOSTILE = ("function modell(p){ try{ localStorage.setItem('pwn','1'); }catch(e){} "
           "try{ parent.document.title='PWNED'; }catch(e){} "
           "const x=[0,1,2,3,4,5]; return {x, serien:[{name:'A', werte:x.map(v=>v*p.zins)}]}; }")

CHART_TAIL = """() => { const c = document.querySelector('.sim canvas');
  return c ? Chart.getChart(c).data.datasets[0].data.slice(-3) : null; }"""
ERROR_TEXT = "() => (document.querySelector('.sim-error') || {}).textContent || null"


def _build(tmp: Path, name: str, code: str | None = None) -> Path:
    from src.unit.assembler import assemble_file
    unit = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    if code is not None:
        unit = copy.deepcopy(unit)
        for lesson in unit["lessons"]:
            for block in lesson.get("blocks", []):
                if block.get("type") == "simulator":
                    block["code"] = code
    src = tmp / f"{name}.json"
    src.write_text(json.dumps(unit, ensure_ascii=False), encoding="utf-8")
    return Path(assemble_file(src, tmp / name).path_)


def _wait(page_or_frame, script, tries=12):
    for _ in range(tries):
        value = page_or_frame.evaluate(script)
        if value:
            return value
        page_or_frame.wait_for_timeout(250)
    return page_or_frame.evaluate(script)


def _open_lesson(browser, path: Path):
    page = browser.new_page()
    page.goto(path.as_uri())
    page.click(f"text={LESSON}")
    return page


def test_shell_in_browser():
    if not installed("playwright"):
        print("  ---  playwright not installed, skipped")
        return
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as t, sync_playwright() as pw:
        tmp = Path(t)
        try:
            browser = pw.chromium.launch()
        except Exception as e:  # noqa: BLE001 — browser binary missing
            print(f"  ---  Chromium not available ({str(e)[:60]}), skipped")
            return

        # 1. Values: compound interest, default parameters, then rate 10 %.
        page = _open_lesson(browser, _build(tmp, "normal"))
        assert _wait(page, CHART_TAIL) == [2288, 2357, 2427]
        page.eval_on_selector_all(".sim input[type=range]",
            "els => { els[1].value = 10; els[1].dispatchEvent(new Event('input')); }")
        page.wait_for_timeout(500)
        assert _wait(page, CHART_TAIL) == [14421, 15863, 17449]
        print("  ok   simulator values match the model and follow the slider")

        # 2. Isolation: hostile simulator code still computes, but cannot
        #    touch the page's storage or title.
        page = _open_lesson(browser, _build(tmp, "hostile", HOSTILE))
        assert _wait(page, CHART_TAIL) == [9, 12, 15]
        assert page.evaluate("localStorage.getItem('pwn')") is None, "storage reached"
        assert "PWNED" not in page.title(), "page title changed by simulator code"
        print("  ok   simulator code cannot reach the page")

        # 3. Errors are shown, not swallowed.
        for code, expected in (("function modell(p){ return {x:[1], serien:[ }", "Simulator-Code"),
                               ("function modell(p){ throw new Error('broken'); }", "broken")):
            page = _open_lesson(browser, _build(tmp, "err", code))
            text = _wait(page, ERROR_TEXT) or ""
            assert expected in text, text
        print("  ok   syntax and runtime errors are reported")

        # 3b. The callout variant is used as a CSS class. Every variant must
        #     have its own style; a renamed variant without a matching rule
        #     falls back to the plain box without any error.
        page = browser.new_page()
        page.goto(_build(tmp, "normal").as_uri())
        colours = page.evaluate("""() => {
            const out = {};
            for (const v of ["key_point", "info", "warning"]) {
                const el = document.createElement("aside");
                el.className = "block note " + v; document.body.appendChild(el);
                out[v] = getComputedStyle(el).backgroundColor; el.remove();
            }
            const plain = document.createElement("aside"); plain.className = "block";
            document.body.appendChild(plain); out.plain = getComputedStyle(plain).backgroundColor;
            return out; }""")
        assert len({colours["key_point"], colours["info"], colours["warning"]}) == 3, colours
        assert colours["plain"] not in (colours["key_point"], colours["warning"]), colours
        print("  ok   every callout variant has its own style")

        # 4. Preview frame: links stay inside the document and the simulator
        #    runs inside the nested sandbox.
        from src.ui.preview import for_preview
        unit_html = _build(tmp, "preview").read_text(encoding="utf-8")
        page = browser.new_page()
        page.route("http://wizard.test/", lambda r: r.fulfill(
            content_type="text/html",
            body=f'<iframe sandbox="allow-scripts" style="width:1000px;height:800px" '
                 f'srcdoc="{html.escape(for_preview(unit_html))}"></iframe>'))
        page.goto("http://wizard.test/")
        page.wait_for_timeout(1000)
        page.frames[1].click(f"text={LESSON}")
        frame = page.frames[1]
        assert frame.evaluate("location.href").startswith("about:srcdoc"), "left the preview"
        assert _wait(frame, CHART_TAIL) == [2288, 2357, 2427]
        print("  ok   preview: links stay in the document, simulator runs nested")
        browser.close()


if __name__ == "__main__":
    test_shell_in_browser()
    print("SHELL BROWSER OK")
