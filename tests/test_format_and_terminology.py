# -*- coding: utf-8 -*-
"""Tests of the normalisation and terminology layer.

Run:  python tests/test_format_and_terminology.py
      python -m pytest tests/test_format_and_terminology.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.unit.normalization import (  # noqa: E402
    latex_simple, normalise_block,
    normalise_html_field, normalise_text_field,
    sup_sub_to_unicode, filter_tags,
)
from src.unit.terminology import (  # noqa: E402
    Terminology, terms_from_text, normal, check_surface)
from src.pipeline.teaching_script import parse_teaching_script  # noqa: E402
from src.pipeline import technical_report as tb  # noqa: E402
from src.pipeline import material_coverage as mab  # noqa: E402
from src.pipeline import job_runner as al  # noqa: E402
import json, tempfile  # noqa: E402
import asyncio  # noqa: E402
from src.unit.terms import mark_terms, mark_unit, slug  # noqa: E402
from src.unit import degradation as degr  # noqa: E402
from src.unit import diagram_types as dtype  # noqa: E402
from src.unit.normalization import secure_mermaid  # noqa: E402
from src.unit.validator import _format_remnants, validate  # noqa: E402


def check(condition, name):
    if condition:
        print(f"  ok   {name}")
        return 0
    print(f"  FAIL {name}")
    return 1


def test_markdown_remnants():
    print("Markdown remnants in HTML fields")
    f = 0
    a, _ = normalise_html_field("<p>Die Norm **ISO/IEC 42001** gilt.</p>")
    f += check("<strong>ISO/IEC 42001</strong>" in a, "**bold** -> <strong>")
    f += check("**" not in a, "no asterisks any more")

    a, _ = normalise_html_field("### Titel\n- eins\n- zwei\n")
    f += check("<h3>Titel</h3>" in a, "# -> <h3>")
    f += check("<ul><li>eins</li><li>zwei</li></ul>" in a, "- -> <ul><li>")

    a, _ = normalise_html_field("<p>Siehe `datei.py` und [Text](https://a.de).</p>")
    f += check("<code>datei.py</code>" in a, "Backticks -> <code>")
    f += check('<a href="https://a.de">Text</a>' in a, "Markdown-Link -> <a>")

    # Code regions stay untouched
    a, _ = normalise_html_field("<pre><code>a = b ** 2\n- kein Listenpunkt</code></pre>")
    f += check("**" in a and "- kein" in a, "code region untouched")
    return f


def test_formulas():
    print("formulas")
    f = 0
    a, _ = normalise_html_field("<p>Das Produkt ($Q \\cdot K^T$) zaehlt.</p>")
    f += check("Q · K<sup>T</sup>" in a, "$Q \\cdot K^T$ -> Unicode + <sup>")
    f += check("$" not in a, "no dollar signs any more")

    a, _ = normalise_html_field("<p>Kosten von $50 pro Monat, $80 im Jahr.</p>")
    f += check("$50" in a and "$80" in a, "currency amount stays (no false alarm)")

    a, _ = normalise_html_field("<p>\\(\\alpha_i^2\\)</p>")
    f += check("α" in a and "<sub>i</sub>" in a and "<sup>2</sup>" in a,
                "\\(…\\) with Greek and indices")

    f += check(latex_simple("\\frac{a}{b}")[1] == "fallback",
                "fraction is marked as a fallback (escalates to MathML)")
    f += check(latex_simple("Q \\cdot K^T")[1] == "good",
                "a simple expression counts as good")
    f += check(latex_simple("\\begin{pmatrix} a \\end{pmatrix}") is None,
                "something unresolvable returns None")

    # Textfelder: Unicode statt Tagverlust
    a, _ = normalise_text_field("Matrix $K^T$ und $x_i$")
    f += check("Kᵀ" in a and "xᵢ" in a, "a text field uses Unicode super/subscripts")
    a, _ = normalise_text_field("Wert $x^{max}$")
    f += check("x^(max)" in a, "cannot be mapped -> caret notation instead of loss")

    blk = {"type": "formula", "latex": "Q \\cdot K^T", "display": "inline",
           "description": "Skalarprodukt aus Query und transponierter Key-Matrix"}
    normalise_block(blk)
    f += check("html" in blk and "<sup>T</sup>" in blk["html"],
                "formula block gets html set")
    f += check(blk["latex"] == "Q \\cdot K^T", "latex stays as the source")
    return f


def test_security_and_allowlist():
    print("Tag-Allowlist")
    f = 0
    a, log_ = filter_tags("<p>Text<script>alert(1)</script></p>")
    f += check("alert" not in a and "<p>" in a, "script removed with its content")
    a, _ = filter_tags('<p onclick="x()">A</p><table><tr><td>B</td></tr></table>')
    f += check("onclick" not in a, "event attribute removed")
    f += check("<table>" not in a and "B" in a, "foreign tag gone, content stays")
    a, _ = filter_tags('<a href="javascript:x">L</a>')
    f += check("javascript" not in a, "javascript URL removed")
    a, _ = filter_tags("<math><mi>x</mi></math>")
    f += check("<math>" in a and "<mi>" in a, "MathML allowed")
    return f


def test_validator_detection():
    print("validator detection")
    f = 0
    f += check(any("Markdown" in str(m) for m in _format_remnants("Die **Norm** gilt")),
                "Markdown remnant detected")
    f += check(any("LaTeX" in str(m) for m in _format_remnants("Wert $Q \\cdot K$")),
                "LaTeX remnant detected")
    f += check(_format_remnants("Der Preis betraegt $50 pro Monat") == [],
                "currency triggers no false alarm")
    f += check(_format_remnants("<code>a ** b</code>") == [],
                "code region excluded")

    unit = {
        "id": "t", "title": "Test", "state": "final", "depth_profile": "compact",
        "lessons": [{"id": "l1", "title": "L1", "concepts": [],
                       "blocks": [{"type": "text", "html": "<p>Die **Norm** gilt.</p>"}]}],
    }
    b = validate(unit, node_probe=False)
    f += check(any("Markdown" in x for x in b.errors),
                "Markdown in the block is reported as an error")
    return f


def test_illustration():
    print("missing illustration")
    text = "<p>" + ("Wort " * 500) + "</p>"
    unit = {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
            "lessons": [{"id": "l1", "title": "L1", "concepts": [],
                           "blocks": [{"type": "text", "html": text}]}]}
    b = validate(unit, node_probe=False)
    f = check(any("illustration" in w for w in b.warnings_),
               "text-heavy lesson without a display is reported")
    unit["lessons"][0]["blocks"].append(
        {"type": "diagram", "engine": "mermaid", "code": "flowchart LR\n A-->B",
         "description": "Ablauf der Bewertung von Antrag bis Entscheidung"})
    b = validate(unit, node_probe=False)
    f += check(not any("illustration" in w for w in b.warnings_),
                "no message any more with a diagram")
    return f


def test_terminology():
    print("terminology")
    f = 0
    t = Terminology()
    t.set_inventory([{"name": "Konformitätsbewertung"}, {"name": "Risikomanagement"}])
    t.set_corpus("Der Anbieter richtet ein Qualitätsmanagementsystem ein und "
                   "dokumentiert die Bewertung der Risiken.")

    f += check(t.covered("Konformitätsbewertung")[1] == "fixed_terms", "inventory term fixed")
    f += check(t.covered("Qualitätsmanagementsystem")[1] == "source", "source term covered")
    f += check(t.covered("Risikomanagementsystem")[0],
                "a legitimate compound produces no false alarm")
    f += check(not t.covered("Konformitätsnachweisführung")[0],
                "coinage is not covered")

    # Surface to check: only what is ESTABLISHED as a term, not every noun.
    unit = {"concepts": [{"id": "k1", "name": "Konformitätsbewertung"}],
            "glossary": [{"term": "Konformitätsnachweisführung", "definition": "…"}],
            "lessons": [{"id": "l1", "blocks": [{"type": "text",
                "html": "<p>Das Leerzeichen trennt Wörter. Unter Silbenfalle "
                        "versteht man einen Segmentierfehler.</p>"}]}]}
    surface = {e["term"] for e in check_surface(unit)}
    f += check("Silbenfalle" in surface, "definition pattern detected")
    f += check("Leerzeichen" not in surface, "everyday word NOT in the surface to check")
    f += check("Konformitätsnachweisführung" in surface, "glossary entry in the surface to check")

    open_ = t.check_unit(unit)
    f += check(any(k["term"] == "Konformitätsnachweisführung" for k in open_),
                "coinage reported")
    f += check(t.covered("Anbieter (KI-Verordnung)")[0] == t.covered("Anbieter")[0],
                "parenthetical addition does not affect coverage")
    f += check(not any(normal(k["term"]) == normal("Leerzeichen") for k in open_),
                "no false alarm on an everyday word")
    f += check(len(t.open_candidates()) >= 1, "candidate registered")

    # Only what is fixed may become binding
    t2 = Terminology()
    t2.set_("Konformitätsbewertung", "…")
    f += check("Konformitätsbewertung" in t2.binding_list(), "fixed is binding")
    t2.check("Der Vertrauenswürdigkeitsgradient steigt.", "k1")
    f += check("Vertrauenswürdigkeitsgradient" not in t2.binding_list(),
                "a candidate does NOT become binding (the core of the design)")

    f += check(normal("Konformitäts-Bewertung") == normal("konformitätsbewertung"),
                "normal form ignores hyphen and capitalisation")
    f += check("Datenqualitätskriterium" in terms_from_text(
        "Unter Datenqualitätskriterium versteht man den Test."), "definition pattern")
    f += check(not terms_from_text("Gleichzeitig beginnt das Kapitel."),
                "a sentence start produces no term")
    return f


def test_teaching_script():
    print("teaching script")
    data_ = {"guiding_question": "…", "common_thread": ["K1: …"], "nodes": [
        {"id": "k1", "introduction": "l1", "requires": []},
        {"id": "k2", "introduction": "l2", "requires": ["k1"], "resumption": ["l3"]},
        {"id": "k3", "introduction": "l1", "requires": ["k2"]}]}
    ls, fnd = parse_teaching_script(data_, {"k1", "k2", "k3", "k4"})
    o = ls.sequence_order()
    f = check(o.index("k1") < o.index("k2") < o.index("k3"),
               "topological order")
    f += check(any("k4" in str(b) for b in fnd), "missing concept reported")
    f += check(any("only introduced in l2" in str(b) for b in fnd),
                "prerequisite after its place of introduction reported")
    ls2, fnd2 = parse_teaching_script({"nodes": [
        {"id": "a", "requires": ["b"]}, {"id": "b", "requires": ["a"]}]}, {"a", "b"})
    f += check(any("cycle" in str(b).lower() for b in fnd2), "cycle detected")
    # Lesson brief: run A writes per concept, run B builds per lesson. A lesson
    # without a concept of its own is a synthesis and must connect instead of
    # repeat — exactly what the redundancy pass reports as a flaw otherwise.
    names3 = {"k1": "Erstes", "k2": "Zweites", "k3": "Drittes"}
    one = ls.job_lesson("l1", ["k1"], names3)
    f += check("INTRODUCES: Erstes" in one, "introducing lesson names its concept")
    syn = ls.job_lesson("l9", ["k1", "k2"], names3)
    f += check("SYNTHESIS LESSON" in syn and "introduces NO new concept" in syn,
                "lesson without a concept of its own is addressed as a synthesis")
    f += check("Repeat NO derivation" in syn,
                "synthesis is bound to connecting instead of repeating")
    mixed = ls.job_lesson("l2", ["k2", "k1"], names3)
    f += check("Only RESUME" in mixed and "Erstes" in mixed,
                "foreign concept in an introducing lesson only for resumption")

    job = ls.job("k2", {"k1": "Erstes", "k2": "Zweites", "k3": "Drittes"})
    f += check("INTRODUCE: Zweites" in job, "brief names its own concept")
    f += check("Erstes" in job and "do NOT derive them again" in job,
                "brief forbids repeating the prerequisite")
    f += check("do not anticipate" in job, "brief forbids anticipation")
    return f


def test_unicode():
    print("Unicode lifting")
    f = check(sup_sub_to_unicode("x<sup>2</sup>") == "x²", "digit lifted")
    f += check(sup_sub_to_unicode("K<sup>T</sup>") == "Kᵀ", "upper-case letter lifted")
    f += check(sup_sub_to_unicode("x<sup>max</sup>") == "x^(max)", "falls back to caret")
    return f


def test_term_marking():
    print("term marking")
    g = [{"term": "Risikomanagement", "short": "…"},
         {"term": "Risikomanagementsystem", "short": "…"},
         {"term": "Anbieter (KI-Verordnung)", "short": "…"}]
    h, n = mark_terms("<p>Das Risikomanagementsystem des Anbieters.</p>", g)
    f = check('data-term="risikomanagementsystem"' in h,
               "longest match wins (not Risikomanagement + rest)")
    f += check("Risikomanagement</span>system" not in h, "no overlap")
    f += check('data-term="anbieter-ki-verordnung"' in h and "Anbieters" in h,
                "inflection detected, parenthetical addition only in the key")
    f += check(n == 2, f"two hits (was {n})")

    h, _ = mark_terms("<pre><code>Risikomanagement</code></pre>", g)
    f += check("<span" not in h, "code zone untouched")
    h, _ = mark_terms("<h3>Risikomanagement</h3>", g)
    f += check("<span" not in h, "heading untouched")
    h, _ = mark_terms('<a href="#x">Risikomanagement</a>', g)
    f += check("<span" not in h, "existing link untouched")

    # Idempotence: marking again does not double
    h1, _ = mark_terms("<p>Das Risikomanagement zählt.</p>", g)
    h2, n2 = mark_terms(h1, g)
    f += check(h1 == h2 and n2 == 0, "idempotent")

    unit = {"glossary": g, "lessons": [{"id": "l1", "blocks": [
        {"type": "text", "html": "<p>Risikomanagement überall.</p>"}]}]}
    f += check(mark_unit(unit) == 1, "mark_unit counts hits")
    f += check(slug("Anbieter (KI-Verordnung)") == "anbieter-ki-verordnung",
                "slug matches the glossary anchor")
    f += check(slug("Naïve Bayes") == "na-ve-bayes",
                "slug does NOT normalise (parity with shell.html)")
    g2 = [{"term": "Freies Morphem"}]
    h, n = mark_terms("<p>Die freien Morpheme sind zahlreich.</p>", g2)
    f += check(n == 1 and 'data-term="freies-morphem"' in h,
                "adjective inflection in multi-word terms")
    return f


def test_mermaid():
    print("Mermaid protection")
    a, p = secure_mermaid("flowchart LR\n  A[Druck (Zugspannung)] --> B[Ende]")
    f = check('A["Druck (Zugspannung)"]' in a, "bracket in the label quoted")
    f += check('(Zugspannung)"]' in a and a.count(")") == 1,
                "closing bracket not swallowed")
    a, _ = secure_mermaid("flowchart LR\n  A[X] -->|Photolyse (Spaltung)| B[Y]")
    f += check('|"Photolyse (Spaltung)"|' in a, "edge label quoted")
    a, p = secure_mermaid('flowchart LR\n  A["Schon (quotiert)"] --> B[Ok]')
    f += check(not p, "already quoted stays untouched")
    a, p = secure_mermaid("flowchart TD\n  A[Ok] --> B[Auch]\n  style A fill:#eee,stroke:#111")
    f += check(not p, "style directive untouched")
    a, _ = secure_mermaid("flowchart TD\n  A(Rund (Zusatz)) --> B{Raute (Frage)}")
    f += check('A("Rund (Zusatz)")' in a and 'B{"Raute (Frage)"}' in a,
                "other node shapes as well")
    # From the diagram application: keywords, multiple diagrams, types that
    # depend on indentation.
    a, _ = secure_mermaid("flowchart LR\n  A[Prozess end] --> B[Der graph zeigt]")
    f += check("end]" not in a and "graph zeigt" not in a,
                "keyword removed as an independent word")
    a, _ = secure_mermaid("flowchart LR\n  A[Ende des Verfahrens] --> B[Graphik]")
    f += check("Ende des Verfahrens" in a and "Graphik" in a,
                "similar words stay untouched")
    a, p = secure_mermaid("flowchart LR\n A-->B\n\nflowchart TD\n C-->D")
    f += check(a.count("flowchart") == 1 and any("diagrams" in x for x in p),
                "only the first diagram stays")
    a, _ = secure_mermaid("mindmap\n  root((Wasser))\n    Aufnahme\n      Wurzel")
    f += check("root((Wasser))" in a and "      Wurzel" in a,
                "mindmap: root shape and indentation kept")
    a, _ = secure_mermaid("flowchart LR\n\n  A-->B\n\n  B-->C")
    f += check("\n\n" not in a, "blank lines removed")
    a, _ = secure_mermaid("flowchart LR\n  A[[Unterprogramm (Teil)]] --> B[X]")
    f += check('A[["Unterprogramm (Teil)"]]' in a, "double bracket shape kept")

    # All Mermaid node shapes must survive the protection INTACT. Otherwise
    # `A([Start])` would become `A("[Start]")` — a stadium turned into a
    # rounded box with visible square brackets, in every diagram of every unit
    # generated.
    forms = ["A([Stadium]) --> B[X]", "A[/Parallelogramm/] --> B[X]",
              "A[" + chr(92) + "Trapez" + chr(92) + "] --> B[X]",
              "A[/Trapez rechts" + chr(92) + "] --> B[X]",
              "A(((Doppelkreis))) --> B[X]", "A((Kreis)) --> B[X]",
              "A{{Sechseck}} --> B[X]", "A[[Unterprogramm]] --> B[X]",
              "A[(Zylinder)] --> B[X]", "A>Fahne] --> B[X]",
              "A{Raute?} --> B[X]", "A[Rechteck] --> B[X]"]
    for form in forms:
        aus, _ = secure_mermaid("flowchart LR\n  " + form)
        f += check(aus.splitlines()[1].strip() == form,
                    f"unchanged: {form.split(' ')[0]}")
    # With risky content it is quoted, but the shape is kept
    aus, _ = secure_mermaid("flowchart LR\n  A([Stadium (Zusatz)]) --> B[X]")
    f += check('A(["Stadium (Zusatz)"])' in aus, "stadium is kept when quoting")
    aus, _ = secure_mermaid("flowchart LR\n  A(((Kreis (Zusatz)))) --> B[X]")
    f += check('A((("Kreis (Zusatz)")))' in aus, "double circle is kept when quoting")

    a, p = secure_mermaid(
        "flowchart TB\n    subgraph G [Titel (Zusatz)]\n      A[X] --> B[Y]\n    end")
    f += check('subgraph G ["Titel (Zusatz)"]' in a, "subgraph title quoted")
    a, p = secure_mermaid("flowchart TB\n  subgraph Einfach\n    A[X]\n  end")
    f += check(not p, "subgraph without brackets untouched")
    a, p = secure_mermaid('flowchart TB\n  subgraph G ["Schon (quotiert)"]\n  end')
    f += check(not p, "quoted subgraph title untouched")

    a, p = secure_mermaid("flowchart LR\n  C --> D[Cortex\n(Apoplast/Symplast)]")
    f += check('D["Cortex<br/>(Apoplast/Symplast)"]' in a,
                "wrapped label merged and quoted")
    f += check(a.count("\n") == 1, "no loose continuation lines any more")
    a, p = secure_mermaid('flowchart LR\n  A["Text mit ] Klammer"] --> B[X]')
    f += check("\n" in a and not any("zusammengefuehrt" in x for x in p),
                "bracket in a quotation triggers no merging")

    blk = {"type": "diagram", "code": "flowchart LR\n  A[Druck (Zug)] --> B[E]",
           "description": "Ablauf des Wassertransports von der Wurzel zum Blatt"}
    normalise_block(blk)
    f += check('"Druck (Zug)"' in blk["code"], "applies through normalise_block")
    return f


def test_vega_interactive():
    print("Vega-Lite interactive")
    def chk(spec, descr="Stelle die Temperatur auf 35 und beobachte die Kurve"):
        unit = {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
                "lessons": [{"id": "l1", "title": "L1", "concepts": [], "blocks": [
                    {"type": "chart", "engine": "vegalite", "description": descr,
                     "spec": spec}]}]}
        return validate(unit, node_probe=False)

    good = {"data": {"values": [{"a": 1}]},
           "params": [{"name": "temp", "value": 20,
                       "bind": {"input": "range", "min": 5, "max": 40, "name": "Temperatur"}}],
           "transform": [{"calculate": "datum.a * temp", "as": "rate"}],
           "mark": "line",
           "encoding": {"y": {"field": "rate", "type": "quantitative"}}}
    b = chk(good)
    f = check(not [x for x in b.errors if "chart" in x or "params" in x],
               "correct interactive spec without errors")

    without_value = {"params": [{"name": "t", "bind": {"input": "range", "min": 0, "max": 9,
                                                    "name": "T"}}], "mark": "line"}
    f += check(any("value" in x for x in chk(without_value).errors),
                "bound parameter without value → error")

    select_empty = {"params": [{"name": "r", "value": "A",
                               "bind": {"input": "select", "name": "Rolle"}}], "mark": "bar"}
    f += check(any("options" in x for x in chk(select_empty).errors),
                "select without options → error")

    signal = {"signal": "x", "mark": "bar"}
    f += check(any("Vega syntax" in x for x in chk(signal).errors),
                "full Vega (signal) is rejected")

    b = chk(good, descr="Zusammenhang zwischen Temperatur und Verdunstungsrate")
    f += check(any("exploration task" in w for w in b.warnings_),
                "interactive graphic without an exploration task → warning")

    # Size policy: vegalite without any params
    unit = {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
            "lessons": [{"id": "l1", "title": "L1", "concepts": [], "blocks": [
                {"type": "chart", "engine": "vegalite", "description": "Ein Balkendiagramm der Werte",
                 "spec": {"mark": "bar", "data": {"values": []}}}]}]}
    f += check(any("1.5 MB" in w for w in validate(unit, node_probe=False).warnings_),
                "static vegalite → size warning")
    return f


def _unit(blk):
    return {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
            "lessons": [{"id": "l1", "title": "L1", "concepts": [], "blocks": [blk]}]}


def test_chart_data():
    print("chart data check")
    v = lambda blk: validate(_unit(blk), node_probe=False)  # noqa: E731
    js = lambda spec: {"type": "chart", "engine": "chartjs",  # noqa: E731
                       "description": "Verteilung der Werte über die Regionen",
                       "spec": spec}
    b = v(js({"type": "bar", "data": {"labels": ["A", "B", "C"],
                                      "datasets": [{"data": [1, 2]}]}}))
    f = check(any("mapping shifts" in x for x in b.errors), "check label/value lengths")
    b = v(js({"type": "bar", "data": {"labels": ["A"], "datasets": [{"data": []}]}}))
    f += check(any("empty" in x for x in b.errors), "leeres dataset")
    b = v(js({"type": "bar", "data": {"labels": list("ABCD"),
                                      "datasets": [{"data": [5, 5, 5, 5]}]}}))
    f += check(any("no difference" in w for w in b.warnings_),
                "constant values reported")

    vg = lambda spec: {"type": "chart", "engine": "vegalite",  # noqa: E731
                       "description": "Stelle den Regler und beobachte die Kurve",
                       "spec": spec}
    b = v(vg({"mark": "bar", "data": {"values": []}}))
    f += check(any("empty" in x for x in b.errors), "leere data.values")
    b = v(vg({"mark": "bar", "data": {"values": [{"a": 1, "b": 2}]},
              "encoding": {"x": {"field": "c", "type": "quantitative"}}}))
    f += check(any("'c' does not occur in the data" in w for w in b.warnings_),
                "unknown field reported")
    b = v(vg({"mark": "bar", "data": {"values": [{"a": 1}]},
              "transform": [{"calculate": "datum.a*2", "as": "d"}],
              "encoding": {"x": {"field": "d", "type": "quantitative"}}}))
    f += check(not [w for w in b.warnings_ if "does not occur in the data" in w],
                "field created by transform accepted")
    b = v(vg({"mark": "bar", "data": {"values": [{"a": 1}]},
              "params": [{"name": "unbenutzt", "value": 1,
                          "bind": {"input": "range", "min": 0, "max": 9, "name": "X"}}],
              "encoding": {"x": {"field": "a", "type": "quantitative"}}}))
    f += check(any("used nowhere" in x for x in b.errors),
                "dead slider reported")
    return f


def test_interaction_logic():
    print("interaction logic")
    v = lambda blk: validate(_unit(blk), node_probe=False)  # noqa: E731
    b = v({"type": "quiz", "questions": [{"question": "F?", "multiple": False, "options": [
        {"text": "A", "correct": True, "feedback": "x"},
        {"text": "A", "correct": False, "feedback": "y"}]}]})
    f = check(any("identical options" in x for x in b.errors), "duplicate options")
    b = v({"type": "quiz", "questions": [{"question": "F?", "multiple": True, "options": [
        {"text": "A", "correct": True, "feedback": "x"},
        {"text": "B", "correct": True, "feedback": "y"}]}]})
    f += check(any("checks nothing" in w for w in b.warnings_),
                "all options correct (warning — does not block)")

    b = v({"type": "cloze", "html": "<p>Das Morphem ist die kleinste Einheit. "
           "Die kleinste bedeutungstragende Einheit heißt {{1}}.</p>",
           "gaps": {"1": {"answers": ["Morphem"]}}})
    f += check(any("can be read off" in w for w in b.warnings_), "gap can be read off")

    b = v({"type": "matching", "task": "Ordne zu",
           "pairs": [{"left": "A", "right": "1"}, {"left": "A", "right": "2"}]})
    f += check(any("left values" in x for x in b.errors), "left not unique")
    b = v({"type": "matching", "task": "Ordne zu",
           "pairs": [{"left": "Xylem", "right": "Xylem"}, {"left": "B", "right": "C"}]})
    f += check(any("trivial pair" in w for w in b.warnings_), "triviales Paar")

    b = v({"type": "flashcards", "cards": [{"front": "Morphem", "back": "A"},
                                           {"front": "morphem", "back": "B"}]})
    f += check(any("duplicate front" in w for w in b.warnings_),
                "duplicate cards (warning — does not block)")
    return f


def test_glossary_coverage_and_breadth():
    print("glossary coverage and breadth")
    basis = {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
             "concepts": [{"id": "k1", "name": "Xylem-Gefäße als Transportweg"}],
             "glossary": [{"term": "Xylem-Gefäße", "definition": "…", "short": "…"}],
             "lessons": [{"id": f"l{i}", "title": "L", "concepts": [],
                            "blocks": [{"type": "text", "html": "<p>Kurz.</p>"},
                                        {"type": "quiz", "questions": [{"question": "F?", "options": [
                                            {"text": "A", "correct": True, "feedback": "x"},
                                            {"text": "B", "correct": False, "feedback": "y"}]}]}]}
                           for i in range(1, 4)]}
    b = validate(basis, node_probe=False)
    f = check(not [w for w in b.warnings_ if "Xylem-Gefäße als Transportweg" in w],
               "term in the concept name counts as covered")
    f += check(any("different forms of display" in w for w in b.warnings_),
                "too little variety of forms reported")

    # Missing short fields as ONE collective message: single warnings would
    # make 69 of 74 warnings with 69 glossary entries and drown everything
    # else.
    many = dict(basis)
    many["glossary"] = [{"term": f"B{i}", "definition": "…"} for i in range(30)]
    bw = [w for w in validate(many, node_probe=False).warnings_ if "short field" in w]
    f += check(len(bw) == 1 and "30 of 30" in bw[0],
                "missing short fields are reported bundled")

    basis["lessons"][0]["blocks"] += [
        {"type": "table", "header": ["A", "B"], "rows": [["1", "2"]],
         "caption": "Übersicht der Werte"},
        {"type": "diagram", "engine": "mermaid", "code": "flowchart LR\n A-->B",
         "description": "Ablauf von A nach B im Überblick"},
        {"type": "code", "language": "python", "content": "x = 1"}]
    b = validate(basis, node_probe=False)
    f += check(any("unevenly distributed" in w for w in b.warnings_),
                "clustering in one lesson reported")
    return f


def test_bare_position_and_categorisation():
    print("bare super/subscript and categorisation")
    from src.unit.normalization import normalise_html_field as _h
    # "q_{m+1}" in a callout must not survive normalisation AND degradation and
    # block the gate.
    a, _ = _h("<p>q_m und q_{m+1} sind Komponenten</p>")
    f = check("q<sub>m+1</sub>" in a, "subscript resolved in HTML")
    a, _ = _h("<p>Datei_{name} bleibt</p>")
    f += check("Datei_{name}" in a, "multi-letter identifier untouched")
    a, _ = _h("<p><code>a_{b}</code></p>")
    f += check("a_{b}" in a, "code region untouched")
    a, _ = normalise_text_field("Ψ_{s} = -0,4 MPa")
    f += check("Ψₛ" in a, "a text field uses Unicode")

    # Categorisation is allowed: several statements, few target terms
    def _z(pairs):
        return {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
                "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
                    {"type": "matching", "task": "Ordne zu", "pairs": pairs}]}]}
    cat = [{"left": f"Aussage {i}", "right": "A" if i % 2 else "B"} for i in range(6)]
    b = validate(_z(cat), node_probe=False)
    f += check(not [x for x in b.errors if "right" in x],
                "categorisation produces no error")
    f += check(not any("Kategorisierung" in w for w in b.warnings_),
                "categorisation produces no routine message")
    one_b = [{"left": f"A{i}", "right": "X"} for i in range(3)]
    f += check(any("nothing to match" in x for x in validate(_z(one_b), node_probe=False).errors),
                "only one target value stays an error")
    return f


def test_findings_from_runs():
    print("findings from real runs")
    from src.unit.normalization import literal_line_breaks, normalise_block
    B = chr(92)

    # 1) Literal escape sequences in task material. The learner would see
    #    "\n\n" in the middle of the text, and the format check would read it
    #    as a
    #    LaTeX command.
    raw = "Eigenkapital: 1.200 TEUR" + B + "n" + B + "nSchritt 1: Steuern"
    new_, log_ = literal_line_breaks(raw)
    f = check(B not in new_ and new_.count(chr(10)) == 2 and log_,
               "literal escape sequences become line breaks")
    blk = {"type": "error_analysis", "title": "T", "material": raw,
           "question": "F", "sample_solution": "M"}
    normalise_block(blk)
    f += check(B not in blk["material"], "material is normalised at all")

    # 2) A constant series NEXT TO a changing one = reference line, not a flaw
    def _c(datasets):
        return {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
                "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
                    {"type": "chart", "engine": "chartjs",
                     "description": "Eine ausreichend lange Beschreibung der Grafik",
                     "spec": {"type": "line", "data": {
                         "labels": ["a", "b", "c", "d"], "datasets": datasets}}}]}]}
    reference = [{"label": "Verlauf", "data": [1, 2, 3, 4]},
                {"label": "Schwelle", "data": [0.05, 0.05, 0.05, 0.05]}]
    w = validate(_c(reference), node_probe=False).warnings_
    f += check(not [x for x in w if "constant" in x or "Werte sind gleich" in x],
                "a reference line is not objected to")
    all_flat = [{"label": "A", "data": [1, 1, 1, 1]}, {"label": "B", "data": [2, 2, 2, 2]}]
    w = validate(_c(all_flat), node_probe=False).warnings_
    f += check(any("constant" in x for x in w),
                "a diagram constant throughout is reported")

    # 3) Parameter addressed as encoding.field — the graphic stays empty
    spec = {"data": {"values": [{"n": 1}]}, "mark": "line",
            "encoding": {"x": {"field": "delta", "type": "quantitative"}},
            "params": [{"name": "delta", "value": 1,
                        "bind": {"input": "range", "name": "Delta"}}]}
    unit = {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
            "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
                {"type": "chart", "engine": "vegalite", "spec": spec,
                 "description": "Eine ausreichend lange Beschreibung der Grafik"}]}]}
    f += check(any("is a PARAMETER" in x
                    for x in validate(unit, node_probe=False).errors),
                "parameter as encoding.field reported")

    # 4) Categorisation no longer produces a routine message
    to = {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
          "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
              {"type": "matching", "task": "Ordne zu", "pairs": [
                  {"left": f"A{i}", "right": "X" if i % 2 else "Y"} for i in range(6)]}]}]}
    f += check(not [x for x in validate(to, node_probe=False).warnings_
                     if "Kategorisierung" in x],
                "categorisation is no longer reported as a routine")
    return f


def test_vega_nested():
    print("Vega-Lite: nested views")
    def _u(spec):
        return {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
                "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
                    {"type": "chart", "engine": "vegalite", "spec": spec,
                     "description": "Eine ausreichend lange Beschreibung der Grafik"}]}]}

    # 'Invalid field type "undefined"' — an encoding without type hidden in
    # vconcat. A check of only the top level would not see it.
    without_type = {"data": {"values": [{"n": 1}]}, "vconcat": [
        {"mark": "line", "encoding": {"x": {"field": "n", "type": "quantitative"}}},
        {"mark": "rule", "encoding": {"y": {"datum": {"expr": "grenze"},
                                            "title": "Grenze"}}}],
        "params": [{"name": "grenze", "value": 2,
                    "bind": {"input": "range", "name": "Grenze"}}]}
    b = validate(_u(without_type), node_probe=False)
    f = check(any("without type" in x for x in b.errors),
               "missing type found in vconcat")

    # Parameter addressed as a data field: draws empty, without a message
    param_as_field = {"data": {"values": [{"n": 1}]},
                      "transform": [{"calculate": "datum.sd / sqrt(datum.n)", "as": "se"}],
                      "mark": "line",
                      "encoding": {"x": {"field": "n", "type": "quantitative"},
                                   "y": {"field": "se", "type": "quantitative"}},
                      "params": [{"name": "sd", "value": 10,
                                  "bind": {"input": "range", "name": "SD"}}]}
    b = validate(_u(param_as_field), node_probe=False)
    f += check(any("is not a data field" in x for x in b.errors),
                "parameter as datum.<name> reported")

    # A correct nested spec stays free of errors
    good = {"data": {"values": [{"n": 1, "se": 2}]},
           "vconcat": [
               {"mark": "line", "encoding": {"x": {"field": "n", "type": "quantitative"},
                                             "y": {"field": "se", "type": "quantitative"}}},
               {"mark": "rule", "encoding": {"y": {"datum": {"expr": "grenze"},
                                                   "type": "quantitative"}}}],
           "params": [{"name": "grenze", "value": 2,
                       "bind": {"input": "range", "name": "Grenze"}}]}
    f += check(not validate(_u(good), node_probe=False).errors,
                "correct nested spec stays free of errors")
    return f


def test_length_bias():
    print("quiz: length bias")
    def _q(pairs):
        return {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
                "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
                    {"type": "quiz", "questions": [
                        {"question": f"F{i}?", "options": [
                            {"text": t_, "correct": (j == k), "feedback": "x"}
                            for j, t_ in enumerate(opts)]}
                        for i, (opts, k) in enumerate(pairs)]}]}]}

    # Correct answer always the longest — in real units 10 out of 12
    lang = [(["short", "auch kurz", "die ausführlich begründete richtige Antwort"], 2)] * 4
    w = [x for x in validate(_q(lang), node_probe=False).warnings_
         if "longest option" in x]
    f = check(w and "4 of 4" in w[0], "consistent length bias reported")

    # Balanced lengths are not objected to
    fair = [(["eine Antwort mittlerer Länge hier", "eine andere Antwort dieser Art",
              "eine dritte Antwort ähnlich lang"], 1)] * 4
    f += check(not [x for x in validate(_q(fair), node_probe=False).warnings_
                     if "longest option" in x],
                "balanced options are not objected to")

    # Below the threshold nothing is reported. What matters is the LENGTH of
    # the correct option, not its position — so in half of the cases the
    # correct one must be the shorter one.
    mixed = ([(["short", "auch kurz", "die ausführlich begründete Antwort"], 2)] * 2
                + [(["die ausführlich begründete falsche Antwort hier",
                     "eine weitere ausführlich begründete falsche Antwort",
                     "richtig"], 2)] * 2)
    w2 = [x for x in validate(_q(mixed), node_probe=False).warnings_
          if "longest option" in x]
    f += check(not w2, "mixed distribution below the threshold")

    # Too few questions: no statement
    f += check(not [x for x in validate(_q(lang[:2]), node_probe=False).warnings_
                     if "longest option" in x],
                "with two questions there is no verdict")

    from src.prompts import learning
    f += check("avoid length bias" in learning.BLOCK_CONTRACT_COMPACT,
                "the rule is in the block contract")
    return f


def test_block_patch():
    print("block patch instead of full revision")
    import json as _json
    from src.pipeline.learning_pipeline import LearningPipeline as _L

    class _LLM:
        def __init__(s, a): s.a = a
        async def complete(s, *args, **kw): return s.a

    class _P(_L):
        language = "de"
        def __init__(s, response):
            s.llm = _LLM(response)
            s.unit = {"depth_profile": "compact"}

    def _les():
        return {"id": "l1", "title": "L", "blocks": [
            {"type": "text", "html": "<p>Unberührter Absatz.</p>"},
            {"type": "quiz", "questions": [{"question": "F?", "options": [
                {"text": "A", "correct": True, "feedback": ""},
                {"text": "B", "correct": False, "feedback": ""}]}]},
            {"type": "text", "html": "<p>Zweiter unberührter Absatz.</p>"}]}

    good = _json.dumps({"replacements": [{"number": 1, "block": {"type": "quiz", "questions": [
        {"question": "F?", "options": [
            {"text": "A", "correct": True, "feedback": "richtig, weil …"},
            {"text": "B", "correct": False, "feedback": "falsch, weil …"}]}]}}]})
    findings = [{"block": 1, "correction": "Feedback ergänzen"}]

    les = _les()
    n, _ = asyncio.run(_P(good)._patch_blocks(les, findings))
    f = check(n == 1, "a valid patch is taken over")
    f += check(les["blocks"][1]["questions"][0]["options"][0]["feedback"],
                "the block objected to is revised")
    f += check(les["blocks"][0]["html"] == "<p>Unberührter Absatz.</p>"
                and les["blocks"][2]["html"] == "<p>Zweiter unberührter Absatz.</p>",
                "blocks not objected to stay literally")

    # Every faulty form of answer leaves the original in place
    for response, name in (
            (_json.dumps({"replacements": [{"number": 1, "block": {
                "type": "text", "html": "<p>x</p>"}}]}), "Typwechsel"),
            (_json.dumps({"replacements": [{"number": 1, "block": {
                "type": "quiz", "questions": []}}]}), "ungültiger Block"),
            (_json.dumps({"replacements": [{"number": 9, "block": {
                "type": "text", "html": "<p>x</p>"}}]}), "Nummer außerhalb"),
            ("", "leere Antwort")):
        les2 = _les()
        n2, _ = asyncio.run(_P(response)._patch_blocks(les2, findings))
        f += check(n2 == 0 and len(les2["blocks"]) == 3
                    and les2["blocks"][1]["type"] == "quiz",
                    f"{name}: the original stays untouched")

    # Without a block reference the patch does not apply — then the full
    # revision follows
    n3, message = asyncio.run(_P(good)._patch_blocks(
        _les(), [{"criterion": "x", "correction": "y"}]))
    f += check(n3 == 0 and "refers to a block" in str(message),
                "a finding without block reference falls back to the full revision")

    # The critic works on the short form, not on the full text
    short = _L._short_form([{"type": "text", "html": "<p>Ein Absatz.</p>"},
                         {"type": "quiz", "questions": []}])
    f += check(short.startswith("[0] text:") and "[1] quiz" in short,
                "the short form numbers the blocks")
    from src.prompts import learning as _l
    p = _l.critic_prompt(short, ["K"], "compact")
    f += check(len(p) < 3000, f"critic prompt stays small ({len(p)} characters)")
    f += check("block number" in p, "the critic must name the block number")
    return f




def test_unit_without_diagram():
    print("unit without any diagram")
    def _u(n_blocks, with_diagram):
        bl = [{"type": "text", "html": "<p>Absatz.</p>"} for _ in range(n_blocks)]
        if with_diagram:
            bl.append({"type": "diagram", "engine": "mermaid",
                       "code": "flowchart LR\n  A-->B",
                       "description": "Der Ablauf im Überblick dargestellt"})
        return {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
                "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": bl}]}

    def _w(u):
        return [x for x in validate(u, node_probe=False).warnings_
                if "not a single diagram" in x]

    # A unit on morphology and phrase structure with 65 blocks and zero
    # diagrams.
    f = check(_w(_u(50, False)), "extensive unit without a diagram is reported")
    f += check(not _w(_u(50, True)), "not objected to with one diagram")
    # Deliberately only the zero case — any threshold in between would be
    # guessed.
    f += check(not _w(_u(20, False)), "a short unit is left alone")
    return f


def test_simulator_probe():
    print("simulators: sliders without effect, empty series")
    import shutil as _sh
    if not _sh.which("node"):
        print("  ---  node missing, probe unchecked")
        return 0

    def _u(code, parameter, output_=None):
        return {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
                "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
                    {"type": "text", "html": "<p>Text.</p>"},
                    {"type": "simulator", "title": "S",
                     "description": "Stelle X ein und beobachte die Kurve",
                     "code": code, "parameters": parameter,
                     "output": output_ or {"kind": "line", "x_label": "Position",
                                            "y_label": "Y"}}]}]}
    par = [{"name": "faktor", "label": "Faktor", "min": 1, "max": 5,
            "step": 1, "value": 2}]

    # Five data points: below that the probe rightly reports a line output as a
    # single point instead of a curve.
    good = ("function modell(p){const x=[1,2,3,4,5];"
           "return {x, series:[{name:'A', values:x.map(v=>v*p.faktor)}]};}")
    w = [x for x in validate(_u(good, par), node_probe=True).warnings_
         if "slider" in x or "series" in x]
    f = check(not w, f"a correct simulator is not objected to ({w[:1]})")

    # Case 1 (fwer concept): slider without any effect
    without = ("function modell(p){const x=[1,2,3];"
            "return {x, series:[{name:'A', values:[1,2,3]}]};}")
    f += check(any("changes nothing" in x for x in
                    validate(_u(without, par), node_probe=True).warnings_),
                "slider without effect is reported")

    # Case 2 (union bound / Bonferroni): series 0 throughout
    null = ("function modell(p){const x=[1,2,3];"
            "return {x, series:[{name:'A', values:x.map(v=>v*p.faktor)},"
            "{name:'Leer', values:[0,0,0]}]};}")
    f += check(any("0 throughout" in x for x in
                    validate(_u(null, par), node_probe=True).warnings_),
                "a series empty throughout is reported")

    # Slider and x axis with the same label
    f += check(any("same label as the x axis" in x for x in
                    validate(_u(good, par, {"kind": "line", "x_label": "Faktor",
                                            "y_label": "Y"}),
                              node_probe=True).warnings_),
                "double use of slider and axis is reported")

    # NaN values break the curve
    nan = ("function modell(p){const x=[1,2,3];"
           "return {x, series:[{name:'A', values:[1, NaN, 3*p.faktor]}]};}")
    f += check(any("NaN or infinite" in x for x in
                    validate(_u(nan, par), node_probe=True).warnings_),
                "non-finite values are reported")

    # A constant series other than 0 is a reference line — no finding
    ref = ("function modell(p){const x=[1,2,3];"
           "return {x, series:[{name:'A', values:x.map(v=>v*p.faktor)},"
           "{name:'Schwelle', values:[5,5,5]}]};}")
    f += check(not [x for x in validate(_u(ref, par), node_probe=True).warnings_
                     if "0 throughout" in x],
                "a reference line other than 0 is not objected to")
    return f



def test_evidence_locations():
    print("terminology verdict gets the occurrences")
    from src.pipeline.learning_pipeline import evidence_locations as _bs
    # For "established technical term or coinage?" the FIRST 6,000 characters
    # are the wrong ones — they contain the scope. What is needed is the
    # context of the terms themselves.
    vt = ("Geltungsbereich. " * 200
          + "Der Turgordruck entsteht durch Wassereinstrom. "
          + "Füllwort. " * 100 + "Die Kavitation unterbricht den Strang. ")
    r = _bs(vt, ["Turgordruck", "Kavitation", "Phantasiewort"], 6000)
    f = check("[Turgordruck]" in r and "Wassereinstrom" in r,
               "an occurring term is delivered with context")
    f += check("[Kavitation]" in r, "also a term far back in the text")
    f += check("[Phantasiewort]" not in r,
                "a term that does not occur produces no occurrence")
    f += check(len(r) <= 6000, "budget kept")
    f += check(len(_bs(vt, [], 500)) == 500, "without terms: the beginning as fallback")
    f += check(_bs("", ["X"]) == "", "leeres Material")
    f += check(_bs(None, ["X"]) == "", "no material")
    unknown = _bs(vt, ["GibtEsNicht"], 400)
    f += check(len(unknown) == 400,
                "no hit: the beginning, because the verdict is 'not evidenced' anyway")

    # No second cut
    prompt = (Path(__file__).resolve().parents[1] / "src" / "prompts"
              / "learning.py").read_text(encoding="utf-8")
    f += check("material[:6000]" not in prompt,
                "no second cut in the prompt")
    return f


def test_script_is_not_truncated():
    print("didactic text is not cut")
    from src.pipeline.learning_pipeline import (MAX_SCRIPT_CONTEXT as _G,
                                           script_structural_substitute as _se)
    assert callable(_se)   # the fallback path this test relies on still exists

    # The script text is written didactically — lead-in, development, example,
    # transition. Shortening it removes precisely the conclusions. Measured:
    # the largest real chapter script has 34,022 characters and gives 12,322
    # tokens of prompt — nine per cent of a 128k window.
    f = check(_G >= 50000, f"the limit is an emergency brake, not a control variable ({_G})")

    class _P:
        detail_plans = {0: {"lessons": [
            {"id": "l1", "title": "Erste Lektion",
             "learning_objectives": ["Kann A erklären"], "content_points": ["Punkt A"]}]}}
        _script_for_prompt = None

    from src.pipeline.learning_pipeline import LearningPipeline as _L
    p = _L.__new__(_L)
    p.detail_plans = _P.detail_plans
    p.chapter_meta = [{"summary": "Das Kapitel führt A ein."}]

    normal = "<h3>Abschnitt</h3><p>" + ("Wort " * 2000) + "</p>"
    f += check(p._script_for_prompt(normal, 0) == normal,
                "a usual script goes UNSHORTENED into the prompt")

    huge = "".join(f"<h3>Kapitel {i}</h3><p>" + ("Wort " * 900) + "</p>"
                     for i in range(20))
    f += check(len(huge) > _G, "the test script exceeds the emergency brake")
    substitute = p._script_for_prompt(huge, 0)
    f += check(substitute != huge[:_G], "in an emergency the prose is NOT cut")
    f += check("OVERVIEW" in substitute and "NOT available" in substitute,
                "the substitute declares itself explicitly as an overview")
    f += check(all(f"Kapitel {i}" in substitute for i in range(20)),
                "all sections are represented in the outline")
    f += check("Kann A erklären" in substitute and "Punkt A" in substitute,
                "learning objectives and content points from the detail plan are included")
    f += check("[…]" not in substitute, "no truncated sentences")
    f += check("Das Kapitel führt A ein." in substitute,
                "the chapter summary is included — it is written as a summary, not cut")
    # Missing fields must not trip it up (resumption, partial states)
    p2 = _L.__new__(_L)
    f += check(p2._script_for_prompt(huge, 0) is not None,
                "missing fields do not stop generation")
    return f


def test_representative_excerpt():
    print("material excerpt shows the cut, not the beginning")
    from src.pipeline.learning_pipeline import representative_excerpt as _ra

    parts = ["Vorwort\n\nDieses Buch behandelt die Bilanzierung. " * 12]
    for i in range(1, 13):
        parts.append(f"\n{i}. Kapitel {i}: Thema {i}\n\n" + f"Fließtext zu Thema {i}. " * 60)
    parts.append("\nZusammenfassung\n\nZentral waren Bewertung und Ausweis.")
    doc = "".join(parts)

    a = _ra(doc)
    chap_new = sum(1 for i in range(1, 13) if f"Kapitel {i}" in a)
    chap_old = sum(1 for i in range(1, 13) if f"Kapitel {i}" in doc[:4000])
    f = check(chap_new == 12, f"all chapters in the excerpt ({chap_new} of 12)")
    f += check(chap_old < 5, f"plain cutting would see only {chap_old} of 12")
    f += check("Zusammenfassung" in a, "the end is included")
    f += check(len(a) <= 4000, f"budget kept ({len(a)})")

    # Edge cases
    f += check(_ra("short") == "short", "a short document stays unchanged")
    f += check(_ra("") == "", "empty document")
    f += check(_ra("x" * 4000) == "x" * 4000, "exactly at the limit unchanged")
    without = _ra("Fließtext ohne jede Gliederung. " * 400)
    f += check(0 < len(without) <= 4000,
                "a document without headings still gives an excerpt")

    # The pipeline uses it as well
    source = (Path(__file__).resolve().parents[1] / "src" / "pipeline"
              / "learning_pipeline.py").read_text(encoding="utf-8")
    f += check("representative_excerpt(t)" in source,
                "the profile collection uses the excerpt")
    f += check("t[:4000] for n, t in" not in source,
                "plain cutting is replaced")
    return f


def test_warnings_reach_repair():
    print("fixable warnings go to the repair")
    from src.pipeline.learning_pipeline import LearningPipeline as _L, _into_pieces
    from src.unit.validator import Finding
    w = Finding()
    w.W("lesson[0](l1).block[3]", "solution '{v1}' appears literally in the surrounding text — "
        "the gap can be read off", code="cloze_readable", v1="X")
    w.W("lesson[0](l1).block[5]", "params[{i}]('{v1}'): binding without name — the control then "
        "carries the technical identifier", code="binding_without_name", i=0, v1="a")
    w.W("lesson[0](l1).block[2]", "interactive graphic: description names no exploration task "
        "(\"Set X to …, observe Y\") — criterion D2", code="no_exploration_task")
    w.W("lesson[0](l1).block[4].questions[0].options[1]", "feedback missing — didactics criterion C3",
        code="no_feedback")
    w.W("unit", "illustration unevenly distributed ({v1} per lesson) — the weakest lesson is "
        "almost text only", v1="2, 1, 3")
    w.W("lesson[0](l1)", "~{w} words of text with {act} interaction(s) and {show} display(s) — too "
        "thin for depth profile 'detailed'. Either developed running text (800–1500 words) or more "
        "activity and illustration", w=400, act=1, show=0)
    w.W("glossary", "{v1} of {v2} entries without a short field (e.g. {v3}) — the hover shows the "
        "full definition there", v1=3, v2=20, v3="x")
    b = _L._fixable_warnings(w)
    f = check(len(b) == 4, f"four block-related warnings detected ({len(b)})")
    f += check(any("feedback missing" in x for x in b), "quiz option without feedback goes to the repair")
    f += check(all("block[" in x for x in b), "only warnings with a block reference")
    f += check(not any("illustration" in x or "too thin" in x or "glossary" in x
                        for x in b),
                "unit-wide findings stay out — they cannot be fixed in one block")

    # Fact check: split into pieces instead of cutting. The end of a lesson
    # contains application and numbers — exactly what must be checked.
    lang = ". ".join(f"Satz Nummer {i} mit etwas Inhalt" for i in range(400)) + "."
    st = _into_pieces(lang, 6000)
    f += check(len(st) >= 2, f"long text is split ({len(st)} pieces)")
    f += check(max(len(x) for x in st) <= 6000, "every piece below the limit")
    f += check(sum(len(x) for x in st) >= len(lang) - len(st),
                "no loss of text when splitting")
    f += check(len(_into_pieces("Kurz.", 6000)) == 1, "short text stays unsplit")
    f += check(_into_pieces("", 6000) == [], "empty text gives no piece")
    return f


def test_contract_tailoring():
    print("block contract as needed")
    from src.prompts import learning as _l
    full = _l.BLOCK_CONTRACT_COMPACT

    # Without a diagram the catalogue is dropped — 29 % of the contract
    without = _l.contract_for(["text", "quiz", "table"])
    f = check(len(without) < len(full) * 0.4, f"clearly shorter without a diagram ({len(without)})")
    f += check("MERMAID DIAGRAM TYPES" not in without, "diagram catalogue is dropped")
    f += check('"type":"quiz"' in without and '"type":"table"' in without,
                "planned types are included")
    f += check('"type":"simulator"' not in without, "unplanned types are dropped")
    f += check("length bias" in without, "general rules stay")

    with_ = _l.contract_for(["text", "diagramm:flowchart", "quiz"])
    f += check("MERMAID DIAGRAM TYPES" in with_, "with a diagram the catalogue stays")

    # FAIL-SAFE: media plans may be written in other languages. An unknown
    # entry must NEVER lead to leaving something out — a missing contract costs
    # the component, one too large only tokens.
    english = _l.contract_for(["text with h3", "table: comparison",
                                "matching: terms", "diagram:classDiagram"])
    f += check('"type":"table"' in english and '"type":"matching"' in english,
                "English media plan entries are translated")
    f += check("MERMAID DIAGRAM TYPES" in english,
                "English 'diagram' keeps the catalogue")
    unclear = _l.contract_for(["text", "irgendein Phantasiebaustein"])
    f += check(unclear == full, "unknown entry → full contract")
    f += check(_l.contract_for([]) == full, "empty plan → full contract")
    f += check(_l.contract_for(None) == full, "no plan → full contract")
    return f



def test_partial_rescue_instead_of_regeneration():
    print("truncated lesson: rescue instead of creating anew")
    import json as _json
    from src.pipeline.learning_pipeline import LearningPipeline as _L

    class _LLM:
        def __init__(s, a): s.a, s.calls_made, s.prompts = a, 0, []
        async def complete(s, prompt, *a, **kw):
            s.calls_made += 1; s.prompts.append(prompt); return s.a

    class _P(_L):
        language = "de"
        def __init__(s, response):
            s.llm = _LLM(response); s.unit = {"depth_profile": "compact"}

    class _T:
        id = "bloecke:1"
        prompt = "Erzeuge die Lektion."
        output = _json.dumps({"id": "l1", "title": "L", "blocks": [
            {"type": "text", "html": "<p>A</p>"},
            {"type": "text", "html": "<p>B</p>"},
            {"type": "quiz", "questions": []},
            {"type": "text", "html": "<p>C</p>"}]})[:-40]

    p = _P(_json.dumps({"further_blocks": [
        {"type": "table", "header": ["A"], "rows": [["1"]], "caption": "X"}]}))
    part = p._partial_lesson(_T.output)
    f = check(part and part.get("blocks"),
               "whatever is valid is rescued from the truncated answer")
    before = len(part["blocks"])
    full = asyncio.run(p._complete_lesson(_T(), part))
    f += check(full and len(full["blocks"]) > before,
                "the completion is appended instead of created anew")
    f += check(p.llm.calls_made == 1, "exactly one call instead of a new generation")
    f += check("ONLY the blocks still MISSING" in p.llm.prompts[0],
                "the prompt asks explicitly only for what is missing")
    f += check("[0] text" in p.llm.prompts[0],
                "existing blocks are named in short form")

    # Unusable remnants are not used any further
    f += check(_P("")._partial_lesson("kein json") is None, "rubbish is discarded")
    f += check(_P("")._partial_lesson(None) is None, "empty output is discarded")
    return f


def test_revision_never_worsens():
    print("a revision must never make things worse")
    from src.pipeline.learning_pipeline import LearningPipeline as _L
    # A critic revision must not delete lessons: a lesson cut off when given
    # in, with an answer replacing the original unconditionally, would pass the
    # chapter validation and only fail at the final gate with "no blocks".
    alt = {"id": "l1", "title": "T",
           "blocks": [{"type": "text", "html": "<p>" + ("Wort " * 400) + "</p>"}]
                      + [{"type": "quiz", "questions": []}] * 5}
    cases = [
        ({"title": "T neu", "blocks": alt["blocks"]}, True, "vollständige Revision"),
        ({}, False, "leere Antwort"),
        ({"title": "T"}, False, "nur Titel, keine Blöcke"),
        ({"title": "T", "blocks": [{"type": "text", "html": "<p>kurz</p>"}]},
         False, "Blöcke verloren"),
        ({"title": "T", "blocks": [{"type": "text", "html": "<p>" + ("Wort " * 100)
                                     + "</p>"}] + [{"type": "quiz", "questions": []}] * 5},
         False, "Text mehr als halbiert"),
        ("Text statt JSON", False, "keine Objektstruktur"),
    ]
    f = 0
    for new_, expected, name in cases:
        ok, reason = _L._revision_acceptable(alt, new_)
        f += check(ok == expected, f"{name}: {'angenommen' if ok else reason}")

    # The cause: revision prompts must not cut the lesson
    source = (Path(__file__).resolve().parents[1] / "src" / "pipeline"
              / "learning_pipeline.py").read_text(encoding="utf-8")
    f += check("json.dumps(lesson, ensure_ascii=False)[:MAX_SCRIPT_CONTEXT]"
                not in source,
                "the revision prompt passes in the lesson unshortened")
    return f


def test_escaped_fields():
    print("HTML rules only for HTML fields")
    # A dash list in the preformatted `material` of an error analysis is the
    # RIGHT display there — <ul><li> would appear literally — and must not
    # block.
    def _u2(blk):
        return {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
                "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
                    {"type": "text", "html": "<p>Text.</p>"}]}],
                "modules": [{"title": "M", "lessons": ["l1"], "exercises": [blk]}]}

    with_list = {"type": "error_analysis", "title": "F", "question": "Was ist falsch?",
                 "material": "Der Lauf zeigt:\n- Erster Punkt\n- Zweiter Punkt",
                 "sample_solution": "Das."}
    b = validate(_u2(with_list), node_probe=False)
    f = check(not [x for x in b.errors if "Markdown list" in x],
               "a dash list in escaped material is not an error")

    # In an HTML field it stays one
    in_html = {"type": "error_analysis", "title": "F",
               "question": "Was ist falsch?\n- Erster Punkt\n- Zweiter Punkt",
               "material": "x", "sample_solution": "Das."}
    f += check(any("Markdown list" in x
                    for x in validate(_u2(in_html), node_probe=False).errors),
                "a dash list in an HTML field stays an error")

    # LaTeX in an escaped field: warning instead of error
    with_latex = {"type": "error_analysis", "title": "F", "question": "F?",
                 "material": "Formel: \\alpha + \\beta", "sample_solution": "Das."}
    b3 = validate(_u2(with_latex), node_probe=False)
    f += check(not [x for x in b3.errors if "LaTeX" in x]
                and any("LaTeX" in x for x in b3.warnings_),
                "LaTeX in an escaped field is a warning")
    return f


def test_gate_selectivity():
    print("selectivity of the gate")
    basis = {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
             "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
                 {"type": "text", "html": "<p>Text.</p>"}]}]}

    # Descriptive concept names cannot have a glossary entry
    descriptive = dict(basis)
    descriptive["concepts"] = [
        {"id": "k1", "name": "Erkennen fragwürdiger Ergebnisdarstellungen"},
        {"id": "k2", "name": "Interpretation von Ergebnistabellen und Abschnitten"},
        {"id": "k3", "name": "Nullhypothese"}]
    descriptive["glossary"] = []
    w = [x for x in validate(descriptive, node_probe=False).warnings_
         if "no glossary entry" in x]
    f = check(len(w) == 1 and "Nullhypothese" in w[0],
               "glossary duty only for term-like concept names")

    # Whatever depends on the environment is bundled and marked as such
    many = dict(basis)
    many["lessons"] = [{"id": f"l{i}", "title": "L", "concepts": [], "blocks": [
        {"type": "diagram", "engine": "mermaid", "code": "flowchart LR\n A-->B",
         "description": "Eine ausreichend lange Beschreibung des Ablaufs"}]}
        for i in range(5)]
    b = validate(many, node_probe=True)   # the probe cannot run here
    env = [x for x in b.warnings_ if x.startswith("umgebung")]
    single = [x for x in b.warnings_ if "not syntax-checked" in x
               and not x.startswith("umgebung")]
    f += check(len(env) <= 1 and not single,
                "a syntax probe that does not run gives exactly one collective message")
    if env:
        f += check("setup problem" in env[0],
                    "a finding about the environment is marked as such")
    return f


def test_html_in_text_fields():
    print("HTML in escaped fields")
    a, p = normalise_text_field("<p>A) Ja, weil Licht das Signal bleibt.</p>")
    f = check("<p>" not in a and "A) Ja, weil" in a, "paragraph tags removed")
    f += check(any("HTML removed" in x for x in p), "intervention logged")
    a, _ = normalise_text_field("Erste Zeile<br>Zweite Zeile")
    f += check("<br>" not in a and "Zeile Zweite" in a, "br becomes whitespace")
    a, _ = normalise_text_field("<p>Eins</p><p>Zwei</p>")
    f += check(a == "Eins Zwei", "sentences do not run together")
    a, _ = normalise_text_field("Wert &lt; 5 und Ψ &amp; MPa")
    f += check("<" in a and "&" in a, "entities resolved")
    a, _ = normalise_text_field("Ganz normaler Text ohne Auszeichnung")
    f += check(a == "Ganz normaler Text ohne Auszeichnung", "unchanged text")

    blk = {"type": "quiz", "questions": [{"question": "<p>Warum?</p>", "options": [
        {"text": "<p>A) Weil</p>", "correct": True, "feedback": "<p>Richtig.</p>"}]}]}
    normalise_block(blk)
    o = blk["questions"][0]["options"][0]
    f += check("<p>" not in o["text"] and "<p>" not in o["feedback"],
                "quiz options cleaned")
    return f


def test_technical_report():
    print("technical report")

    class _C:
        model, total_calls = "modell-x", 7
        total_input_tokens, total_output_tokens = 1000, 250

    class _P:
        llm = _C()
        llm_fast = _C()
        losses = ["eine Lektion"]
        terminology = None
        teaching_script = None

    unit = {"title": "T", "duration_minutes": 30,
            "concepts": [{"id": "k1", "name": "A", "concept_class": "V"}],
            "glossary": [{"term": "A", "definition": "…"}],
            "lessons": [{"id": "l1", "blocks": [
                {"type": "text", "html": "<p>" + ("Wort " * 100) + "</p>"},
                {"type": "quiz", "questions": []},
                {"type": "diagram", "code": "flowchart LR\n A-->B"}]}]}
    md, data_ = tb.report(unit, _P())
    f = check("Technical report" in md, "Markdown produced")
    f += check(data_["content"]["Lessons"] == 1, "lessons counted")
    f += check(data_["content"]["Words of reading text"] == 100, "words counted")
    f += check(data_["ratios"]["Interactions"] == 1, "interactions counted")
    f += check(data_["ratios"]["Displays"] == 1, "displays counted")
    f += check(data_["history"]["Lost lessons"] == 1, "losses recorded")
    # Identical clients must not be counted twice
    _P.llm_fast = _P.llm
    _, d2 = tb.report(unit, _P())
    f += check(len(d2["llm"]) == 1, "the same client counted only once")
    f += check("modell-x" in md, "model name in the report")
    f += check(tb.as_json(data_).startswith("{"), "JSON serialisable")
    # An empty unit must not crash
    md2, _ = tb.report({}, None)
    f += check("Technical report" in md2, "empty unit without a crash")
    return f


def test_material_coverage():
    print("material coverage")

    class _E:
        def __init__(s, i, t_, kind, kw, txt):
            s.id, s.title, s.kind = i, t_, kind
            s.keywords, s.summary, s.full_text = kw, txt, txt
            s.document = "quelle.pdf"

    class _Idx:
        """Scores by word overlap — behaves like a reranker."""
        def __init__(s, e, source="reranker"):
            s._entries, s.source = e, source

        async def retrieve_scored(s, q, top_k=5):
            qw = {w.lower() for w in q.split() if len(w) > 4}
            out = []
            for e in s._entries:
                hw = {w.lower() for w in
                      (e.title + " " + " ".join(e.keywords) + " " + e.full_text).split()}
                out.append((e, min(0.95, len(qw & hw) / max(len(qw), 1) * 1.6), s.source))
            return sorted(out, key=lambda x: -x[1])[:top_k]

    entries = [_E("M01", "Turgordruck im Zellinneren", "Definition",
                    ["Turgordruck", "Zellwasserhaushalt"],
                    "Turgordruck entsteht im Zellwasserhaushalt der Pflanzenzelle"),
                 _E("M02", "Randnotiz zur Geschichte", "Beispiel", ["Anekdote"],
                    "Eine historische Nebenbemerkung ohne Fachbezug")]
    concepts = [{"id": "k1", "name": "Turgordruck und Zellwasserhaushalt",
                 "rationale": "tragend"},
                {"id": "k2", "name": "Quantenmechanische Tunneleffekte", "rationale": "x"}]

    m = asyncio.run(mab.matrix(concepts, _Idx(entries)))
    a1, a2 = m["coverage"]
    f = check(a1.evidenced and a1.safe, "evidenced concept detected")
    f += check(not a2.evidenced and a2.provenance() == "model_knowledge",
                "unevidenced concept falls below the threshold")
    f += check([v["id"] for v in m["orphaned"]] == ["M02"],
                "material without a concept reported")
    f += check("EVIDENCE FROM THE MATERIAL" in mab.evidence_block(a1),
                "evidence block for the author")
    f += check("none found in the uploaded material" in mab.evidence_block(a2),
                "unevidenced is named explicitly")

    # Without a reranker: a ranking, but no decision
    m2 = asyncio.run(mab.matrix(concepts, _Idx(entries, source="cosine")))
    f += check(not m2["reranker"], "missing reranker is shown")
    f += check(m2["coverage"][0].provenance() == "material_unchecked",
                "a cosine hit counts as unchecked")
    f += check("not as evidence" in mab.as_markdown(m2),
                "the caveat is in the report")
    without_index = asyncio.run(mab.matrix(concepts, None))
    f += check(len(without_index["coverage"]) == 2
                and all(a.provenance() == "model_knowledge" for a in without_index["coverage"]),
                "without an index everything counts as model knowledge")
    return f


def test_degradation():
    print("degradation instead of blocking")
    def _u(blocks):
        return {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
                "lessons": [{"id": "l1", "title": "L1", "concepts": [],
                               "blocks": blocks}]}

    unit = _u([{"type": "text", "html": "<p>Text.</p>"},
               {"type": "chart", "engine": "vegalite",
                "description": "Verlauf der Zielgröße über den Zeitraum",
                "spec": {"mark": "bar", "data": {"values": []}}}])
    b = validate(unit, node_probe=False)
    f = check(len(b.errors) == 1, "a broken chart produces an error")
    replaced = degr.downgrade(unit, b)
    f += check(len(replaced) == 1, "block was replaced")
    f += check(not validate(unit, node_probe=False).errors,
                "free of errors afterwards — the unit stays deliverable")
    substitute = unit["lessons"][0]["blocks"][1]
    f += check(substitute["type"] == "note" and "Zielgröße" in substitute["html"],
                "the description stays as text")

    # Interactions are NOT replaced — otherwise one fakes completeness
    unit2 = _u([{"type": "text", "html": "<p>T.</p>"},
                {"type": "quiz", "description": "Eine ausreichend lange Beschreibung",
                 "questions": []}])
    b2 = validate(unit2, node_probe=False)
    f += check(b2.errors and not degr.downgrade(unit2, b2),
                "a quiz is not replaced away")

    # Invented block types: downgrade instead of block
    unit5 = _u([{"type": "text", "html": "<p>T.</p>"},
                {"type": "interactive", "title": "Regler",
                 "html": "<p>Stelle den Wert ein und beobachte die Wirkung.</p>"}])
    b5 = validate(unit5, node_probe=False)
    f += check(any("Unbekannter Blocktyp" in x or "unknown block type" in x
                    for x in b5.errors), "an invented type produces an error")
    f += check(len(degr.downgrade(unit5, b5)) == 1
                and not validate(unit5, node_probe=False).errors,
                "an invented type is downgraded")
    f += check("Stelle den Wert" in unit5["lessons"][0]["blocks"][1]["html"],
                "content rescued from substitute fields")

    # The original must SURVIVE the downgrade. Otherwise the rescue destroys
    # the cause: the broken source would be nowhere to be found afterwards, and
    # Mermaid errors could not be investigated.
    unit6 = _u([{"type": "text", "html": "<p>T.</p>"},
                {"type": "diagram", "engine": "mermaid", "code": "erDiagram\n  DOKUMENT",
                 "description": "Beziehungsdiagramm der zentralen Entitäten"}])
    b6 = validate(unit6, node_probe=False)
    degr.downgrade(unit6, b6)
    f += check(len(degr.discarded) == 1, "the discarded block is kept")
    if degr.discarded:
        v = degr.discarded[0]
        f += check(v["block"].get("code") == "erDiagram\n  DOKUMENT",
                    "the source stays in the original")
        f += check(v["findings"] and "relation" in v["findings"][0],
                    "the triggering finding is carried along")
    # A second run starts with an empty list
    degr.downgrade(_u([{"type": "text", "html": "<p>T.</p>"}]),
                  validate(_u([{"type": "text", "html": "<p>T.</p>"}]), node_probe=False))
    f += check(not degr.discarded, "the list is reset per run")

    # Without a usable description the error remains
    unit3 = _u([{"type": "text", "html": "<p>T.</p>"},
                {"type": "chart", "engine": "vegalite", "description": "short",
                 "spec": {"mark": "bar", "data": {"values": []}}}])
    b3 = validate(unit3, node_probe=False)
    f += check(not degr.downgrade(unit3, b3),
                "no substitute without a usable description")

    # Didactic flaws do not block
    unit4 = _u([{"type": "quiz", "questions": [{"question": "F?", "multiple": True, "options": [
        {"text": "A", "correct": True, "feedback": "x"},
        {"text": "B", "correct": True, "feedback": "y"}]}]}])
    b4 = validate(unit4, node_probe=False)
    f += check(any("checks nothing" in w for w in b4.warnings_)
                and not any("checks nothing" in x for x in b4.errors),
                "all-options-correct is a warning now")
    return f


def test_job_runner():
    print("decoupled production")

    class _P:
        class stop_signal:
            is_stopped = False
            @staticmethod
            def stop(): _P.stop_signal.is_stopped = True

    async def _run():
        tmp = Path(tempfile.mkdtemp())
        folder = tmp / "job-0007-test"
        (folder / "dist").mkdir(parents=True)
        (folder / "state.json").write_text(
            json.dumps({"job": 7, "gap": {"title": "Testauftrag"}}), encoding="utf-8")

        async def work(run):
            for i in range(3):
                run.notify(f"Schritt {i}", phase=f"Kapitel {i}/3", share=i / 3)
                await asyncio.sleep(0.01)
            run.notify("Abschluss", phase="Abschluss", share=1.0)

        run = al.start(7, folder, _P(), work)
        duplicate = al.start(7, folder, _P(), work) is run
        await asyncio.sleep(0.15)
        status = json.loads((folder / "run-status.json").read_text(encoding="utf-8"))
        return run, duplicate, status, al.overview(tmp)

    run, duplicate, status, ue = asyncio.run(_run())
    f = check(duplicate, "no double start of the same job")
    f += check(run.status() == "done" and run.share == 1.0, "run finished")
    f += check("Schritt 0" in run.log_lines and "Abschluss" in run.log_lines,
                "log buffered")
    f += check(status["status"] == "done", "status file written")
    f += check(ue and ue[0]["title"] == "Testauftrag", "job in the overview")
    f += check(al.get_(999) is None and not al.abort(999),
                "unknown job without a crash")

    # Errors end up in the run, not in the stack
    async def _error():
        tmp = Path(tempfile.mkdtemp())
        (tmp / "o").mkdir()
        async def broken(run):
            raise RuntimeError("absichtlich")
        run = al.start(11, tmp / "o", _P(), broken)
        await asyncio.sleep(0.05)
        return run
    lf = asyncio.run(_error())
    f += check(lf.status() == "error" and "absichtlich" in (lf.errors or ""),
                "an exception becomes the run status")
    return f


def test_enrichment_robust():
    print("enrichment against contaminated output")
    from src.pipeline.learning_pipeline import LearningPipeline

    class _LLM:
        def __init__(s, a): s.a = a
        async def complete(s, *args, **kw): return s.a

    class _P(LearningPipeline):
        language = "de"
        def __init__(s, response):
            s.teaching_script = None; s.gap = None; s.llm = _LLM(response)
            s.enriched = 0; s.enrichment_discarded = 0; s.unit = {}

    def _run(response):
        les = {"id": "l1", "title": "L",
               "blocks": [{"type": "text", "html": "<p>" + "Wort " * 500 + "</p>"}]}
        return asyncio.run(_P(response)._enrich(les, {"media_plan": ["quiz"]})), les

    # Strings instead of objects would break the whole chapter with "'str'
    # object has no attribute 'get'".
    n, les = _run('{"neue_bloecke": ["nur ein String", "noch einer"]}')
    f = check(n == 0 and len(les["blocks"]) == 1, "strings instead of objects are discarded")

    n, les = _run('{"neue_bloecke": ["Müll", {"nach_block": "x", "block": '
                   '{"typ":"tabelle","kopf":["A","B"],"zeilen":[["1","2"]],'
                   '"beschriftung":"Übersicht der Werte im Vergleich"}}, {"block": null}]}')
    f += check(n == 1 and les["blocks"][-1]["type"] == "table",
                "a valid block is taken over despite rubbish next to it")
    n, _ = _run('{"neue_bloecke": "gar keine Liste"}')
    f += check(n == 0, "new_blocks as a string")
    n, _ = _run("")
    f += check(n == 0, "empty answer")
    return f


def test_embedder_outage():
    print("embedder failure")
    # httpx is missing in the test environment — mock it; the client needs only
    # its type, not its function.
    import importlib.util
    if "httpx" not in sys.modules and importlib.util.find_spec("httpx") is None:
        import types as _t
        m = _t.ModuleType("httpx")
        m.AsyncClient = object
        m.__getattr__ = lambda a: object  # type: ignore[attr-defined]
        sys.modules["httpx"] = m
    from src.pipeline.inventory import EmbedderClient

    class _A:
        def __init__(s, code, data_=None): s.status_code, s._d = code, data_ or {}
        def json(s): return s._d

    class _C:
        def __init__(s, models=None): s.posts, s.models = [], models
        async def post(s, url, **kw):
            s.posts.append(url); return _A(404)
        async def get(s, url, **kw):
            return _A(200, {"data": [{"id": m} for m in s.models]}) if s.models else _A(404)

    def _new(models):
        c = EmbedderClient.__new__(EmbedderClient)
        c.base_url = "https://beispiel.invalid/v1"
        c.api_key, c.model = "k", "m"
        c._endpoint, c._unavailable = None, False
        c._client = _C(models)
        return c

    c = _new(["modell-a"])
    v = asyncio.run(c.embed(["a", "b"]))
    f = check(v == [[], []], "empty vectors instead of an exception")
    attempts = len(c._client.posts)
    asyncio.run(c.embed(["c"]))
    f += check(len(c._client.posts) == attempts,
                "no new attempt after unsuccessful detection")
    f += check(len(set(c._client.posts)) == len(c._client.posts),
                "no duplicate candidate paths")
    f += check(c._unavailable, "failure is remembered")

    # Successful detection must keep working
    class _COk(_C):
        async def post(s, url, **kw):
            s.posts.append(url)
            return _A(404) if url.endswith("/embeddings") else _A(200, {"data": []})
    c2 = _new(None); c2._client = _COk(None)
    asyncio.run(c2.embed(["x"]))
    f += check(c2._endpoint and c2._endpoint.endswith("/embed"),
                "an alternative path is detected")
    return f


def test_diagram_types():
    print("diagram types")
    f = check(len(dtype.TYPES) >= 12, f"{len(dtype.TYPES)} types in the registry")

    # Detection including alias and upper/lower case
    for code, expected in (("flowchart LR\n A-->B", "flowchart"),
                           ("graph TD\n A-->B", "flowchart"),
                           ("stateDiagram\n [*] --> A\n A --> B: x", "stateDiagram-v2"),
                           ("  mindmap\n root((X))\n   Ast", "mindmap"),
                           ("völlig anderes\n foo", None)):
        f += check(dtype.detect(code) == expected, f"recognises {expected or 'nothing'}")

    # Minimal structure: passes the syntax, but shows the learner nothing
    f += check(dtype.structure_finding("flowchart LR\n  A[Nur ein Kasten]"),
                "flowchart without an edge is reported")
    f += check(not dtype.structure_finding("flowchart LR\n  A-->B"),
                "flowchart with an edge is fine")
    f += check(dtype.structure_finding('pie title X\n  A 60'),
                "pie without values is reported")
    f += check(not dtype.structure_finding('pie title X\n  "A" : 60'),
                "pie with values is fine")
    f += check(not dtype.structure_finding("sankey-beta\n  A,B,30"), "Sankey with a flow")
    f += check(dtype.indentation_matters("mindmap\n root((X))")
                and not dtype.indentation_matters("flowchart LR\n A-->B"),
                "dependency on indentation from the registry")

    # The validator uses the registry
    unit = {"id": "t", "title": "T", "state": "final", "depth_profile": "compact",
            "lessons": [{"id": "l1", "title": "L", "concepts": [], "blocks": [
                {"type": "diagram", "engine": "mermaid", "code": "flowchart LR\n  A[Allein]",
                 "description": "Eine ausreichend lange Beschreibung des Diagramms"}]}]}
    b = validate(unit, node_probe=False)
    f += check(any("no edge" in x for x in b.errors),
                "the validator reports an empty diagram")
    unit["lessons"][0]["blocks"][0]["code"] = "kein gültiger Start\n  foo"
    f += check(any("not recognised" in x for x in validate(unit, node_probe=False).errors),
                "unknown diagram type is reported")

    # All three prompts must know the types — PLANNING chooses the type,
    # GENERATION writes the syntax. If it is missing in the detail plan,
    # flowchart arises by reflex, whatever the block contract offers.
    from src.prompts import learning as _l
    detail_plan = _l.detail_plan_prompt({"title": "K", "concepts": [], "learning_objectives": []},
                                  [], {"context": "a"}, "detailed")
    contract = _l.BLOCK_CONTRACT_COMPACT
    enrich = _l.enrichment_prompt("x", "y", "z", contract)
    for name, p in (("Feinplan", detail_plan), ("Blockvertrag", contract),
                    ("Anreicherung", enrich)):
        missing = [k for k in dtype.TYPES if k not in p]
        f += check(not missing, f"{name} knows all types"
                    + (f" (fehlen: {missing[:3]})" if missing else ""))
        f += check("{_DIAGRAMM" not in p and "__DIAGRAMM" not in p,
                    f"{name} without unreplaced placeholders")
    f += check("[*] -->" in contract and "[*] -->" not in detail_plan,
                "syntax scaffolds only in generation, not in planning")
    f += check("diagram:stateDiagram-v2" in detail_plan,
                "the media plan example names a type")
    # Every type needs all five description fields — without didactic use and
    # degrees of freedom a model produces the most primitive form of every type
    # and does not choose it by the learning activity.
    incomplete = [k for k, v in dtype.TYPES.items()
                      if not (v.purpose and v.didactics and v.not_when
                              and v.degrees_of_freedom and v.scaffold)]
    f += check(not incomplete, f"all types fully described"
                + (f" (fehlt bei {incomplete})" if incomplete else ""))
    full = dtype.prompt_catalog()
    f += check(all(x in full for x in ("Didactic use", "Degrees of freedom", "Scaffold")),
                "the generation catalogue carries use, degrees of freedom and scaffold")
    short = dtype.prompt_catalog_short()
    f += check("Use:" in short and "Scaffold" not in short,
                "the planning catalogue carries the use but no syntax")
    # Every scaffold must pass its own structure check
    bad = [k for k, v in dtype.TYPES.items() if dtype.structure_finding(v.scaffold)]
    f += check(not bad, "every scaffold passes its own structure check"
                + (f" (nicht: {bad})" if bad else ""))
    # and be recognised by its own key
    wrong = [k for k, v in dtype.TYPES.items() if dtype.detect(v.scaffold) != k]
    f += check(not wrong, "every scaffold is recognised as its type"
                + (f" (nicht: {wrong})" if wrong else ""))
    return f


if __name__ == "__main__":
    errors = sum([
        test_markdown_remnants(), test_formulas(), test_security_and_allowlist(),
        test_validator_detection(), test_illustration(), test_terminology(),
        test_teaching_script(), test_term_marking(), test_mermaid(), test_diagram_types(), test_vega_interactive(), test_chart_data(),
        test_interaction_logic(), test_html_in_text_fields(), test_gate_selectivity(), test_escaped_fields(), test_revision_never_worsens(), test_partial_rescue_instead_of_regeneration(), test_contract_tailoring(), test_warnings_reach_repair(), test_representative_excerpt(), test_script_is_not_truncated(), test_evidence_locations(), test_simulator_probe(), test_unit_without_diagram(), test_block_patch(), test_length_bias(), test_vega_nested(), test_findings_from_runs(), test_bare_position_and_categorisation(), test_glossary_coverage_and_breadth(), test_technical_report(), test_material_coverage(), test_degradation(), test_job_runner(), test_enrichment_robust(), test_embedder_outage(),
        test_unicode(),
    ])
    print(f"\n{'ALL TESTS PASSED' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
