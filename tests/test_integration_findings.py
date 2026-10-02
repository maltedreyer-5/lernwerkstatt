# -*- coding: utf-8 -*-
"""Integration tests for findings from real runs.

Each test takes the route the application really takes — field alias,
normalisation, validation — instead of asking a single function.
"""
import json
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _m in ("openai", "httpx"):
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            _mod = types.ModuleType(_m)
            _mod.__getattr__ = lambda a: object  # type: ignore[attr-defined]
            sys.modules[_m] = _mod

from src.pipeline.learning_pipeline import _resolve_field_aliases  # noqa: E402
from src.unit.validator import validate  # noqa: E402


def check(b, name):
    print(f"  {'ok  ' if b else 'FAIL'} {name}")
    return 0 if b else 1


def _unit(blocks, depth="compact", **rest):
    u = {"id": "t", "title": "T", "state": "final", "depth_profile": depth,
         "lessons": [{"id": "l1", "title": "L", "concepts": [],
                        "blocks": blocks}]}
    u.update(rest)
    return u


def test_1_alt_text_alias():
    """Diagrams without alternative text would block delivery.

    The cause is not missing text but a FIELD NAME: the model writes
    `beschriftung` instead of `description`. With `table`, however,
    `caption` is a field of its own and legitimate — the alias must depend
    on the type.
    """
    print("1 · alternative text through a field alias")
    raw = {"type": "diagram", "engine": "mermaid", "code": "flowchart LR\n  A-->B",
           "caption": "Der Ablauf des Signifikanztests im Überblick"}
    blk = _resolve_field_aliases(dict(raw))
    f = check(blk.get("description") and "caption" not in blk,
               "diagram: beschriftung becomes description")

    # The whole route: alias resolved → validation free of errors
    u = _unit([{"type": "text", "html": "<p>Text.</p>"}, blk])
    f += check(not [x for x in validate(u, node_probe=False).errors
                     if "alternative text" in x],
                "no alternative-text error afterwards")

    # Without resolution it still fails — so the test checks something
    u_raw = _unit([{"type": "text", "html": "<p>Text.</p>"}, dict(raw)])
    f += check(any("alternative text" in x for x in
                    validate(u_raw, node_probe=False).errors),
                "without resolution the error remains")

    # table keeps its own caption
    tab = _resolve_field_aliases({"type": "table", "header": ["A"], "rows": [["1"]],
                                "caption": "Vergleich der Verfahren"})
    f += check(tab.get("caption") == "Vergleich der Verfahren"
                and not tab.get("description"),
                "table: caption stays untouched")
    for another in ("alt", "caption", "bildunterschrift"):
        b2 = _resolve_field_aliases({"type": "chart", "engine": "chartjs", "spec": {},
                                   another: "Verlauf der Messwerte über die Zeit"})
        f += check(bool(b2.get("description")), f"chart: {another} is recognised")
    return f


def test_2_scope_judged_together():
    """Warnings 'too few words' must not hit dense, short lessons.

    A word count check independent of activity and illustration would ask
    for the opposite of the interaction density check, which asks for more
    exercises with more text.
    """
    print("2 · length judged together with activity")
    text = {"type": "text", "html": "<p>" + ("Wort " * 300) + "</p>"}
    quiz = {"type": "quiz", "questions": [{"question": "F?", "options": [
        {"text": "A", "correct": True, "feedback": "x"},
        {"text": "B", "correct": False, "feedback": "y"}]}]}
    tab = {"type": "table", "header": ["A", "B"], "rows": [["1", "2"]],
           "caption": "Vergleich"}

    def _thin(blocks):
        return [x for x in validate(_unit(blocks, "detailed"),
                                     node_probe=False).warnings_ if "too thin" in x]

    f = check(_thin([text]), "short and without activity is reported")
    f += check(_thin([text, quiz]), "short with one exercise is reported")
    f += check(not _thin([text, quiz, quiz, quiz]),
                "short with three exercises counts as dense")
    f += check(not _thin([text, quiz, tab, tab, tab, tab]),
                "short with an exercise and four displays counts as dense")

    # No message with depth profile 'compact'
    f += check(not [x for x in validate(_unit([text]), node_probe=False).warnings_
                     if "too thin" in x],
                "compact profile is left alone")
    return f


def test_3_cloze_rule():
    """Warnings 'solution appears literally in the surrounding text'.

    The check finds it reliably; the prompt must also say that the solution
    must not appear in the visible text of the same exercise.
    """
    print("3 · cloze: rule in the contract and the check applies")
    from src.prompts import learning
    rule = "CLOZE — the most frequent source of errors"
    f = check(rule in learning.BLOCK_CONTRACT_COMPACT, "the rule is in the block contract")
    f += check(rule in learning.enrichment_prompt("x", "y", "z",
                                                  learning.BLOCK_CONTRACT_COMPACT),
                "the rule also reaches the enrichment")
    f += check("WRONG:" in learning.BLOCK_CONTRACT_COMPACT
                and "RIGHT:" in learning.BLOCK_CONTRACT_COMPACT,
                "the rule names a counter-example and a positive example")

    readable = {"type": "cloze",
                "html": "<p>Die vier Felder heißen True Positives und True "
                        "Negatives. Korrekt erkannte Effekte sind {{1}}.</p>",
                "gaps": {"1": {"answers": ["True Positives"]}}}
    f += check(any("can be read off" in x for x in
                    validate(_unit([readable]), node_probe=False).warnings_),
                "a gap that can be read off is reported")

    clean = {"type": "cloze",
              "html": "<p>Ein Test erkennt einen echten Effekt korrekt. Dieses "
                      "Feld der Vierfeldertafel heißt {{1}}.</p>",
              "gaps": {"1": {"answers": ["True Positives"]}}}
    f += check(not [x for x in validate(_unit([clean]), node_probe=False).warnings_
                     if "can be read off" in x],
                "a correct gap is not objected to")
    return f


def test_4_node_dependencies():
    """Mermaid must not fail with 'DOMPurify.addHook is not a function'.

    The cause is a version incompatibility: jsdom from version 25 on calls
    `webidl.util.markAsUncloneable`, which exists only from Node 22 on. The
    base image brings Node 20 (Debian trixie). The versions are in
    package.json and are installed exactly like that in the image with
    `npm ci`.
    """
    print("4 · Node dependencies pinned")
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["dependencies"]
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    exact = re.compile(r"^\d+\.\d+\.\d+$")
    f = check(bool(exact.match(package.get("jsdom", ""))), "jsdom is pinned to a version")
    f += check(int((package.get("jsdom") or "99").split(".")[0]) <= 24,
                "the jsdom version is compatible with Node below 22")
    f += check("markAsUncloneable" in docker,
                "the cause is documented in the Dockerfile")
    f += check(bool(exact.match(package.get("dompurify", ""))), "dompurify pinned as well")
    f += check("npm ci" in docker and (ROOT / "package-lock.json").exists(),
                "the image installs exactly from the lockfile")

    app = (ROOT / "app.py").read_text(encoding="utf-8")
    f += check("node --version" in app or '"--version"' in app,
                "start-up diagnosis reports the Node version")

    # The probe must set exit code 1 on a fatal finding, otherwise the
    # build-time check has no effect.
    probe = (ROOT / "assets" / "mermaid_probe.mjs").read_text(encoding="utf-8")
    f += check("process.exitCode = 1" in probe,
                "the Mermaid probe signals failure through the exit code")
    f += check("domReason" in probe,
                "the probe reports the reason instead of swallowing it")
    return f


def test_5_normalization_destroys_no_content():
    """Flashcards with an empty front in a lesson on tokenisation.

    The cause would be the normalisation itself: `<s>`, `</s>`, `<pad>` and
    `<unk>` are the SUBJECT MATTER there, but look like HTML tags. The rule:
    if nothing is left after removal, it was not markup but content.
    """
    print("5 · normalisation destroys no content")
    from src.unit.normalization import normalise_text_field as ntf
    f = 0
    for token in ("<s>", "</s>", "<pad>", "<unk>", "<mask>", "<b></b>"):
        f += check(ntf(token)[0] == token, f"{token} is kept")
    # Real markup is still removed
    f += check(ntf("Das <b>Wichtige</b> hier")[0] == "Das Wichtige hier",
                "real markup is still removed")
    f += check(ntf("<p>A) Ja, weil …</p>")[0] == "A) Ja, weil …",
                "block tags are still removed")

    from src.unit.normalization import normalise_block
    cards = {"type": "flashcards", "cards": [
        {"front": "<s>", "back": "Markiert den Beginn einer Sequenz."},
        {"front": "<pad>", "back": "Füllt kürzere Sequenzen auf."}]}
    normalise_block(cards)
    f += check(all(k["front"] for k in cards["cards"]),
                "flashcards keep their front")
    f += check(not validate(_unit([cards]), node_probe=False).errors,
                "and pass validation")
    return f


def test_6_invented_block_types():
    """`grafik` instead of `chart`/`diagram` must not end up in degradation.

    The content would be rescued, but the form of display lost — a diagram
    would become a paragraph. The type can be determined from the content.
    """
    print("6 · invented block types are mapped")
    f = 0
    for raw, expected in (
            ({"type": "grafik", "code": "flowchart LR\n A-->B"}, "diagram"),
            ({"type": "grafik", "spec": {"mark": "bar"}}, "chart"),
            ({"type": "karteikarten", "cards": []}, "flashcards"),
            ({"type": "table", "header": ["A"], "rows": [["1"]]}, "table"),
            ({"type": "matching", "pairs": []}, "matching"),
            ({"type": "text", "html": "<p>ok</p>"}, "text")):
        f += check(_resolve_field_aliases(dict(raw))["type"] == expected,
                    f"{raw['type']} → {expected}")
    # Without usable content there is NO guessing
    f += check(_resolve_field_aliases({"type": "grafik", "html": "<p>x</p>"})["type"]
                == "grafik", "without a clue the type stays untouched")
    return f


def test_7_controls_labelled():
    """`params[0]('alpha_slider'): binding without name`.

    A warning nobody fixes, although the label can be derived
    deterministically from the parameter name.
    """
    print("7 · controls are named")
    from src.unit.normalization import normalise_block
    blk = {"type": "chart", "engine": "vegalite", "description": "x",
           "spec": {"params": [
               {"name": "alpha_slider", "value": 0.05, "bind": {"input": "range"}},
               {"name": "anzahl_tests", "value": 20,
                "bind": {"input": "range", "name": "Anzahl Tests m:"}}]}}
    normalise_block(blk)
    p = blk["spec"]["params"]
    f = check(p[0]["bind"]["name"] == "Alpha", "alpha_slider becomes Alpha")
    f += check(p[1]["bind"]["name"] == "Anzahl Tests m:",
                "an existing label stays untouched")
    f += check(not [x for x in validate(_unit([blk]), node_probe=False).warnings_
                     if "binding without name" in x],
                "no warning afterwards")
    return f


if __name__ == "__main__":
    errors = (test_1_alt_text_alias() + test_2_scope_judged_together()
              + test_3_cloze_rule() + test_4_node_dependencies()
              + test_5_normalization_destroys_no_content()
              + test_6_invented_block_types() + test_7_controls_labelled())
    print(f"\n{'INTEGRATION OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
