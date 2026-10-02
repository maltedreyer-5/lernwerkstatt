# -*- coding: utf-8 -*-
"""Normalises LLM output to the HTML lead format of the LernWerkstatt.

HTML is the lead format: the script phase delivers HTML, `shell.html`
inserts it, `_html_to_md` converts back for the Word handout. Models drift
regularly into Markdown (`**bold**`) and LaTeX (`$x^2$`) despite
instructions — both appear literally in the delivered unit.

This layer repairs that deterministically BEFORE the validator checks. The
usual case therefore costs no retry; the validator only reports what could
not be resolved here.

Field classes that `shell.html` treats differently:
  * HTML fields are inserted raw (`${b.html}`) -> CONVERT markers.
  * Text fields go through `esc()` -> REMOVE markers (HTML would be visible
    literally there as well).
  * Taboo fields (code, Mermaid source, chart spec) stay untouched.

Formulas follow the step rule: the simplest sufficient display first.
`Q \\cdot K^T` becomes `Q · K<sup>T</sup>` — readable, searchable,
accessible, without any library. Only what cannot be displayed like that
(fractions, sums with limits, matrices) goes to KaTeX and becomes MathML.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

_ASSETS = Path(__file__).resolve().parents[2] / "assets"

# ── Field classes per block type
# ────────────────────────────────────────────────
# Paths are tuples: ("field",) directly, ("list", "field") for lists of dicts,
# ("list", "*") for lists of strings.

FIELDS_HTML: dict[str, list[tuple]] = {
    "text": [("html",)],
    "note": [("html",)],
    "accordion": [("items", "html")],
    "cloze": [("html",)],
    "simulator": [("explanation",)],
    "prediction": [("question",), ("resolution",)],
    "task": [("task",), ("sample_solution",), ("hints", "*")],
    "error_analysis": [("question",), ("sample_solution",)],
}

FIELDS_TEXT: dict[str, list[tuple]] = {
    "table": [("caption",), ("header", "*"), ("rows", "**")],
    "accordion": [("items", "title")],
    "quiz": [("questions", "question")],
    # The shell renders these fields escaped; without normalisation Markdown
    # remnants and literal escape sequences in them would reach the learner.
    # tests/test_field_coverage.py compares the renderer's fields with these
    # lists.
    "matching": [("task",), ("pairs", "left"), ("pairs", "right")],

    "flashcards": [("cards", "front"), ("cards", "back")],
    "chart": [("description",)],
    "diagram": [("description",)],
    "formula": [("description",)],
    "simulator": [("title",), ("description",),
                  # `parameters` is a list of objects, `output` a single object
                  # with x_label/y_label — not symmetrical.
                  ("parameters", "label"), ("parameters", "unit"),
                  ("output", "x_label"), ("output", "y_label")],
    "widget": [("title",), ("description",)],
    "prediction": [("options", "text"), ("options", "feedback")],
    # `material` is rendered as escaped text in <pre> and therefore belongs
    # here. Without it literal "\\n" sequences would show in the task text, and
    # the format check would read them as a LaTeX command.
    "task": [("title",), ("material",)],
    "error_analysis": [("title",), ("material",)],
}

# Never touch: source code and specifications.
FIELDS_TABOO = {
    ("code", "content"), ("diagram", "code"), ("simulator", "code"),
    ("chart", "spec"), ("widget", "html"), ("formula", "latex"),
    ("cloze", "gaps"),
}

# Allowed tags in HTML fields (level contracts + formula markup).
ALLOWED_TAGS = {
    "p", "strong", "em", "ul", "ol", "li", "a", "code", "br", "h3", "h4",
    "sub", "sup", "span",
    # MathML Core — rendered natively by all current browsers.
    "math", "semantics", "annotation", "mrow", "mi", "mn", "mo", "msup",
    "msub", "msubsup", "mfrac", "msqrt", "mroot", "mtext", "munderover",
    "munder", "mover", "mtable", "mtr", "mtd", "mspace", "mstyle",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "span": {"class"},
    "math": {"display", "xmlns"},
    "annotation": {"encoding"},
    "mo": {"stretchy", "separator", "fence"},
    "mspace": {"width"},
    "mstyle": {"displaystyle"},
}

# ── LaTeX detection ───────────────────────────────────────────────────────
# The primary signal is the backslash command, not the dollar sign: "$50" must
# not produce a hit. `$…$` only counts as a formula if the content contains a
# backslash or a super/subscript.
_MATH_BRACKET = re.compile(r"\\\((.+?)\\\)", re.S)
_MATH_BRACKET_D = re.compile(r"\\\[(.+?)\\\]", re.S)
_MATH_DOLLAR_D = re.compile(r"\$\$(.+?)\$\$", re.S)
_MATH_DOLLAR = re.compile(r"(?<!\$)\$([^$\n]{1,200})\$(?!\$)")
_LOOKS_LIKE_MATH = re.compile(r"[\^_]|\\[a-zA-Z]+")


_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "phi": "φ", "chi": "χ", "psi": "ψ",
    "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
_SYMBOLS = {
    "cdot": "·", "times": "×", "div": "÷", "pm": "±", "mp": "∓",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝",
    "infty": "∞", "partial": "∂", "nabla": "∇", "forall": "∀",
    "exists": "∃", "in": "∈", "notin": "∉", "subset": "⊂",
    "subseteq": "⊆", "cup": "∪", "cap": "∩", "emptyset": "∅",
    "rightarrow": "→", "to": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "Leftarrow": "⇐", "leftrightarrow": "↔", "Leftrightarrow": "⇔",
    "ldots": "…", "dots": "…", "cdots": "⋯", "prime": "′",
    "circ": "∘", "deg": "°", "percent": "%", "ast": "∗", "star": "⋆",
    "langle": "⟨", "rangle": "⟩", "|": "|", ",": " ", ";": " ", "quad": " ",
    "qquad": "  ", "%": "%", "&": "&amp;", "#": "#", "_": "_",
}


def _esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


_UPPER_MAP = dict(zip(
    "0123456789+-=()aeioruvxnABDEGHIJKLMNOPRTUVW",
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ᵃᵉⁱᵒʳᵘᵛˣⁿᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ"))
_LOWER_MAP = dict(zip(
    "0123456789+-=()aeioruvxhklmnpst",
    "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢₒᵣᵤᵥₓₕₖₗₘₙₚₛₜ"))


def sup_sub_to_unicode(html: str, strip_tags: bool = True) -> str:
    """Lifts sub/sup to Unicode.

    Only groups that can be mapped completely are lifted; otherwise the
    caret/underscore notation stays, so that `x^T` does not silently become
    `xT`.

    `strip_tags=True` (default) for fields that go through `esc()` — every
    tag would be visible literally there. `False` for the HTML->Markdown
    path, where the other tags are still needed.
    """
    def _um(m, card, mark):
        content = m.group(1)
        if content and all(c in card for c in content):
            return "".join(card[c] for c in content)
        return f"{mark}{content}" if len(content) == 1 else f"{mark}({content})"
    t = re.sub(r"<sup>([^<]*)</sup>", lambda m: _um(m, _UPPER_MAP, "^"), html)
    t = re.sub(r"<sub>([^<]*)</sub>", lambda m: _um(m, _LOWER_MAP, "_"), t)
    return re.sub(r"<[^>]+>", "", t) if strip_tags else t


# ── Level 1: simple formulas as HTML (sub/sup + Unicode) ────────────────

def latex_simple(tex: str) -> tuple[str, str] | None:
    """Converts simple LaTeX into HTML with sub/sup and Unicode.

    Returns (html, quality) with quality in {"good", "fallback"}, or None if
    a command that cannot be resolved remains — then level 2 (MathML) is
    responsible. "fallback" marks constructions that belong in two
    dimensions (fractions, roots): set linearly they are readable, but MathML
    is better when it is available.
    """
    t = (tex or "").strip()
    if not t:
        return None
    quality = "good"
    # \text{…}, \mathrm{…}, \mathbf{…} etc. -> Inhalt
    t = re.sub(r"\\(?:text|mathrm|mathbf|mathit|mathsf|operatorname)\s*\{([^{}]*)\}",
               r"\1", t)
    # \sqrt{x} -> √(x); \frac{a}{b} -> (a)/(b) — only as a fallback
    if re.search(r"\\(?:sqrt|frac|sum|int|prod|lim|binom)\b", t):
        quality = "fallback"
    t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", t)
    t = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", t)
    # Symbols and Greek letters
    def _sym(m):
        name = m.group(1)
        if name in _SYMBOLS:
            return _SYMBOLS[name]
        if name in _GREEK:
            return _GREEK[name]
        return m.group(0)
    t = re.sub(r"\\([a-zA-Z]+|[,;|%&#_])", _sym, t)
    # Super/subscript: ^{…} / ^x and _{…} / _x
    t = re.sub(r"\^\s*\{([^{}]*)\}", lambda m: f"<sup>{_esc(m.group(1))}</sup>", t)
    t = re.sub(r"\^\s*([A-Za-z0-9+\-])", lambda m: f"<sup>{_esc(m.group(1))}</sup>", t)
    t = re.sub(r"_\s*\{([^{}]*)\}", lambda m: f"<sub>{_esc(m.group(1))}</sub>", t)
    t = re.sub(r"_\s*([A-Za-z0-9+\-])", lambda m: f"<sub>{_esc(m.group(1))}</sub>", t)
    # Unresolved commands or bracket structures -> level 2
    if re.search(r"\\[a-zA-Z]+|[{}]", t):
        return None
    # Escape remaining special characters without destroying the tags created
    parts = re.split(r"(</?su[bp]>)", t)
    t = "".join(p if re.fullmatch(r"</?su[bp]>", p) else _esc(p) for p in parts)
    t = t.strip()
    return (t, quality) if t else None


# ── Level 2: MathML via KaTeX (Node, at build time) ───────────────────────

_katex_available: bool | None = None


def katex_present() -> bool:
    global _katex_available
    if _katex_available is None:
        _katex_available = bool(
            shutil.which("node") and (_ASSETS / "mathml_probe.mjs").exists()
            and _mathml_call(["x"]) is not None
        )
    return _katex_available


def _mathml_call(formulas: list[str], display: bool = False) -> list[dict] | None:
    node = shutil.which("node")
    if node is None or not (_ASSETS / "mathml_probe.mjs").exists():
        return None
    try:
        proc = subprocess.run(
            [node, str(_ASSETS / "mathml_probe.mjs")],
            input=json.dumps({"formulas": formulas, "display": display}),
            capture_output=True, text=True, timeout=20,
        )
        data_ = json.loads(proc.stdout.strip() or "{}")
        if data_.get("fatal"):
            return None
        return data_.get("results")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def latex_to_mathml(tex: str, display: bool = False) -> str | None:
    res = _mathml_call([tex], display=display)
    if not res:
        return None
    e = res[0]
    return e.get("mathml") if e.get("ok") else None


def formel_html(tex: str, display: bool = False) -> tuple[str, str]:
    """Best available display of a formula — the step rule for formulas.

    1. Simple notation as HTML (sub/sup + Unicode): readable, searchable,
       accessible, without a library. Covers the usual case.
    2. MathML via KaTeX for everything two-dimensional.
    3. Raw LaTeX code as a visible remnant — the validator reports it.

    Returns (html, stage) with stage in {"simple", "mathml", "raw"}.
    """
    simple = latex_simple(tex)
    if simple and simple[1] == "good" and not display:
        return f'<span class="formula">{simple[0]}</span>', "simple"
    mathml = latex_to_mathml(tex, display=display)
    if mathml:
        return mathml, "mathml"
    if simple:
        return f'<span class="formula">{simple[0]}</span>', "simple"
    return f'<code class="formula-raw">{_esc(tex)}</code>', "raw"


# ── Protected regions (code must never be normalised) ────────────────────

_PROTECTION = re.compile(r"(<code\b.*?</code>|<pre\b.*?</pre>|<math\b.*?</math>)",
                     re.S | re.I)


def _with_protection(text: str, fn):
    parts = _PROTECTION.split(text or "")
    log_lines: list[str] = []
    for i, t in enumerate(parts):
        if i % 2 == 0:
            parts[i], p = fn(t)
            log_lines += p
    return "".join(parts), log_lines


# ── Formulas in running text ─────────────────────────────────────────────────

def replace_formulas(text: str) -> tuple[str, list[str]]:
    log_: list[str] = []

    def _block(m):
        html, stage = formel_html(m.group(1).strip(), display=True)
        log_.append(f"Blockformel -> {stage}")
        return html

    def _inline(m):
        html, stage = formel_html(m.group(1).strip(), display=False)
        log_.append(f"inline formula -> {stage}")
        return html

    def _inline_dollar(m):
        content = m.group(1)
        if not _LOOKS_LIKE_MATH.search(content):
            return m.group(0)          # "$50" stays untouched
        return _inline(m)

    t = text or ""
    t = _MATH_DOLLAR_D.sub(_block, t)
    t = _MATH_BRACKET_D.sub(_block, t)
    t = _MATH_BRACKET.sub(_inline, t)
    t = _MATH_DOLLAR.sub(_inline_dollar, t)
    return t, log_


# ── Markdown-Reste ────────────────────────────────────────────────────────

_MD_TABLE = re.compile(r"^\s*\|.+\|\s*$", re.M)


_BARE_POSITION = re.compile(
    r"(?<![\w])([A-Za-z\u03b1-\u03c9\u0391-\u03a9])([\^_])\{([^{}]{1,12})\}")


def bare_position_to_html(text: str) -> tuple[str, list[str]]:
    """Resolves LaTeX super/subscripts without delimiters in HTML fields.

    Models write "q_{m+1}" not only into text fields but also in the middle
    of HTML — into a callout, for instance. Unresolved it stays literally,
    and the validator reports it as a format remnant. The distinction is
    made by the SINGLE-LETTER base identifier: "q_{m+1}" is a formula,
    "Datei_{name}" an identifier that stays untouched.
    """
    log_: list[str] = []

    def _um(m):
        tag = "sup" if m.group(2) == "^" else "sub"
        log_.append(f"super/subscript -> <{tag}>")
        return f"{m.group(1)}<{tag}>{_esc(m.group(3))}</{tag}>"

    return _BARE_POSITION.sub(_um, text or ""), log_


def md_to_html(text: str) -> tuple[str, list[str]]:
    """Converts Markdown remnants in HTML fields."""
    log_: list[str] = []
    t = text or ""

    if _MD_TABLE.search(t):
        log_.append("Markdown table found — belongs in a table block")

    # Headings (h1/h2 are not allowed -> h3)
    def _head(m):
        stage = min(max(len(m.group(1)), 3), 4)
        log_.append("Markdown-Ueberschrift")
        return f"<h{stage}>{m.group(2).strip()}</h{stage}>"
    t = re.sub(r"^(#{1,6})\s+(.+?)\s*#*$", _head, t, flags=re.M)

    # Links before emphasis (otherwise the * rule eats bracket contents)
    def _link(m):
        log_.append("Markdown-Link")
        return f'<a href="{m.group(2)}">{m.group(1)}</a>'
    t = re.sub(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)", _link, t)

    def _mark(pattern, substitute, name):
        nonlocal t
        new_, n = re.subn(pattern, substitute, t)
        if n:
            log_.append(f"{name} ({n}x)")
            t = new_

    _mark(r"\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*", r"<strong>\1</strong>", "Markdown fett")
    _mark(r"(?<![\w*])__(?!\s)([^_\n]+?)(?<!\s)__(?![\w*])", r"<strong>\1</strong>",
          "Markdown fett (Unterstrich)")
    _mark(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>",
          "Markdown kursiv")
    _mark(r"`([^`\n]+)`", r"<code>\1</code>", "Markdown Code")

    # Lists: collect contiguous blocks
    def _list(m):
        rows = [re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", z)
                  for z in m.group(0).strip().splitlines()]
        tag = "ol" if re.match(r"^\s*\d+\.", m.group(0).lstrip()) else "ul"
        log_.append(f"Markdown-Liste ({tag})")
        return f"<{tag}>" + "".join(f"<li>{z.strip()}</li>" for z in rows) + f"</{tag}>"
    t = re.sub(r"(?:^[ \t]*(?:[-*+]|\d+\.)[ \t]+.+$\n?)+", _list, t, flags=re.M)

    # Remove horizontal rules (no hr in the contract)
    t = re.sub(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$\n?", "", t, flags=re.M)

    return t, log_


_HTML_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")


def strip_html(text: str) -> tuple[str, list[str]]:
    """Removes HTML from fields that `shell.html` sends through `esc()`.

    Every tag appears literally there — as "<p>A) Ja, weil …</p>" in the
    middle of an answer option. Block ends become whitespace, so that
    sentences do not run together.
    """
    if "<" not in (text or "") and "&" not in (text or ""):
        return text or "", []
    # Lift super- and subscripts to Unicode first, otherwise "H<sub>2</sub>O"
    # becomes "H2O" when the tags are removed.
    t = sup_sub_to_unicode(text or "", strip_tags=False)
    t = re.sub(r"</(p|div|li|h[1-6])\s*>", " ", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", " ", t, flags=re.I)
    names = sorted({m.group(1).lower() for m in _HTML_TAG.finditer(t)})
    t = _HTML_TAG.sub("", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
         .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    t = re.sub(r"[ \t]{2,}", " ", t).strip()

    # Protection against self-destruction: if nothing is left after removal
    # although there were characters before, that was not markup but the
    # CONTENT. In a lesson on tokenisation "<s>", "</s>", "<pad>" and "<unk>"
    # are exactly the subject matter — removing them would leave flashcards
    # with empty fronts.
    if (text or "").strip() and not t:
        return text, ["HTML removal discarded: the field would otherwise consist of whitespace only — the content merely looks like a tag"]
    return t, ([f"HTML removed: {', '.join(names)}"] if names else [])


def strip_md(text: str) -> tuple[str, list[str]]:
    """Removes Markdown markers in escaped text fields (converting would be
    pointless there, because `esc()` would show every tag literally)."""
    log_: list[str] = []
    t = text or ""
    for pattern, substitute, name in (
        # The same CommonMark strictness as in the validator: "** p < .01, ***"
        # (APA
        # asterisks) is not bold and must never be stripped.
        (r"\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*", r"\1", "fett"),
        (r"(?<![\w*])__([^_\n]+?)__(?![\w*])", r"\1", "fett"),
        (r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"\1", "kursiv"),
        (r"`([^`\n]+)`", r"\1", "Code"),
        (r"^#{1,6}\s+", "", "Ueberschrift"),
    ):
        new_, n = re.subn(pattern, substitute, t, flags=re.M)
        if n:
            log_.append(f"marker removed: {name} ({n}x)")
            t = new_
    # Formulas in text fields: only the simple level, tags would be visible.
    # sub/sup are lifted to Unicode, so that "x^2" does not become "x2".
    def _f(m):
        content = m.group(1).strip()
        if not _LOOKS_LIKE_MATH.search(content):
            return m.group(0)
        simple = latex_simple(content)
        if not simple:
            return m.group(0)
        log_.append("formula -> plain text")
        return sup_sub_to_unicode(simple[0])
    # Bare LaTeX super/subscripts without delimiters: models write "q_{m+1}" in
    # the middle of a description. Unresolved it appears literally, and the
    # validator reports it as a format remnant. The distinction is made by the
    # SINGLE-LETTER base identifier: "q_{m+1}" is a formula, "Datei_{name}" an
    # identifier that stays untouched.
    def _location(m):
        basis, mark, content = m.group(1), m.group(2), m.group(3)
        tag = "sup" if mark == "^" else "sub"
        log_.append("super/subscript -> Unicode")
        return basis + sup_sub_to_unicode(f"<{tag}>{content}</{tag}>")

    t = re.sub(r"(?<![\w])([A-Za-z\u03b1-\u03c9\u0391-\u03a9])([\^_])\{([^{}]{1,12})\}", _location, t)

    t = _MATH_DOLLAR.sub(_f, t)
    t = _MATH_BRACKET.sub(lambda m: _f(m) if _LOOKS_LIKE_MATH.search(m.group(1)) else m.group(0), t)
    return t, log_


# ── Tag-Allowlist ─────────────────────────────────────────────────────────

_TAG = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)((?:\s[^<>]*)?)/?\s*>")


_DANGEROUS = re.compile(
    r"<\s*(script|style|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>|"
    r"<\s*(script|style|iframe|object|embed)\b[^>]*/?>",
    re.S | re.I)


def filter_tags(html: str) -> tuple[str, list[str]]:
    """Removes tags outside the allowlist (the content is kept).

    Exception: with script/style/iframe/object/embed the content is removed
    as well — there it is executable code, not reading text.
    """
    removed: set[str] = set()

    def _danger(m):
        removed.add((m.group(1) or m.group(2) or "?").lower())
        return ""
    html = _DANGEROUS.sub(_danger, html or "")

    def _t(m):
        name = m.group(2).lower()
        if name not in ALLOWED_TAGS:
            removed.add(name)
            return ""
        attrs = m.group(3) or ""
        allowed = ALLOWED_ATTRIBUTES.get(name, set())
        filtered = []
        for am in re.finditer(r'([a-zA-Z-]+)\s*=\s*"([^"]*)"', attrs):
            if am.group(1).lower() in allowed:
                value = am.group(2)
                if am.group(1).lower() == "href" and not re.match(
                        r"^(https?:|mailto:|#)", value):
                    continue
                filtered.append(f'{am.group(1)}="{value}"')
        space = (" " + " ".join(filtered)) if filtered else ""
        return f"<{m.group(1)}{name}{space}>"

    new_ = _TAG.sub(_t, html or "")
    log_ = [f"tag removed: <{n}>" for n in sorted(removed)] if removed else []
    return new_, log_


# ── Normalisation per field ──────────────────────────────────────────────

def normalise_html_field(value: str) -> tuple[str, list[str]]:
    def _stage(t):
        t, p1 = replace_formulas(t)
        t, p2 = md_to_html(t)
        t, p3 = bare_position_to_html(t)
        return t, p1 + p2 + p3
    t, log_ = _with_protection(value, _stage)
    t, p3 = filter_tags(t)
    return t, log_ + p3


_LITERAL_LINE_BREAKS = re.compile(r"\\[nrt]")


def literal_line_breaks(text: str) -> tuple[str, list[str]]:
    """Turns literal escape sequences into real characters.

    Models occasionally write "\\n" into text fields as a visible character
    sequence instead of a line break. The learner then sees "\\n\\n" literally
    in the middle of the task text, and the format check also reports it as
    a LaTeX command.
    """
    if not _LITERAL_LINE_BREAKS.search(text or ""):
        return text or "", []
    replaced = (text.replace(f"\\n", chr(10))
                   .replace(f"\\r", "")
                   .replace(f"\\t", " "))
    return replaced, ["literale Escape-Folge in echten Umbruch gewandelt"]


def normalise_text_field(value: str) -> tuple[str, list[str]]:
    t, p0 = literal_line_breaks(value)
    t, p1 = strip_html(t)
    t, p2 = strip_md(t)
    return t, p0 + p1 + p2


def _set(container, path_: tuple, fn, log_: list[str], path_txt: str) -> None:
    """Applies `fn` to a field according to the path description."""
    if len(path_) == 1:
        field_ = path_[0]
        if isinstance(container.get(field_), str):
            new_, p = fn(container[field_])
            if new_ != container[field_]:
                container[field_] = new_
                log_ += [f"{path_txt}.{field_}: {x}" for x in p]
        return
    list_, under = path_[0], path_[1]
    entries = container.get(list_)
    # Two-level path into an OBJECT instead of a list — ("output", "x_label")
    # with the simulator, for instance. Without this branch the normalisation
    # would silently miss it.
    if isinstance(entries, dict):
        if isinstance(entries.get(under), str):
            new_, p = fn(entries[under])
            if new_ != entries[under]:
                entries[under] = new_
                log_ += [f"{path_txt}.{list_}.{under}: {x}" for x in p]
        return
    if not isinstance(entries, list):
        return
    for i, e in enumerate(entries):
        if under == "*" and isinstance(e, str):
            new_, p = fn(e)
            if new_ != e:
                entries[i] = new_
                log_ += [f"{path_txt}.{list_}[{i}]: {x}" for x in p]
        elif under == "**" and isinstance(e, list):
            for j, z in enumerate(e):
                if isinstance(z, str):
                    new_, p = fn(z)
                    if new_ != z:
                        e[j] = new_
                        log_ += [f"{path_txt}.{list_}[{i}][{j}]: {x}" for x in p]
        elif isinstance(e, dict) and isinstance(e.get(under), str):
            new_, p = fn(e[under])
            if new_ != e[under]:
                e[under] = new_
                log_ += [f"{path_txt}.{list_}[{i}].{under}: {x}" for x in p]


def _name_vega_bindings(spec: dict) -> list[str]:
    """Adds missing labels to Vega-Lite controls.

    Without `name` the slider carries its technical identifier —
    "alpha_slider" instead of "Alpha". A readable label can be derived
    deterministically from the parameter name; that needs no model and no
    warning nobody fixes.
    """
    log_: list[str] = []
    for p in (spec.get("params") or []):
        if not isinstance(p, dict) or not isinstance(p.get("bind"), dict):
            continue
        if (p["bind"].get("name") or "").strip():
            continue
        raw = str(p.get("name") or "").strip()
        if not raw:
            continue
        # "alpha_slider" -> "Alpha", "anzahl_tests" -> "Anzahl Tests"
        parts = [w for w in re.split(r"[_\-\s]+", raw)
                 if w and w.lower() not in ("slider", "regler", "input", "param")]
        p["bind"]["name"] = " ".join(w[:1].upper() + w[1:] for w in parts) or raw
        log_.append(f"Bedienelement benannt: {raw} -> {p['bind']['name']}")
    return log_


def normalise_block(blk: dict, path_txt: str = "block") -> list[str]:
    """Normalises a block in place. Returns a log."""
    log_: list[str] = []
    if not isinstance(blk, dict):
        return log_
    type_ = blk.get("type")
    # Controls without a label otherwise carry the technical identifier.
    if type_ == "chart" and isinstance(blk.get("spec"), dict):
        log_ += [f"{path_txt}: {x}" for x in _name_vega_bindings(blk["spec"])]
    # Formula blocks: LaTeX stays as the source, `html` carries the display.
    # That makes the unit renderable without a run-time library, and the
    # formula stays editable for later rework. Mermaid: secure labels before
    # the validator parses. Prevents the most frequent syntax error
    # deterministically instead of only reporting it.
    if type_ == "diagram" and isinstance(blk.get("code"), str):
        new_, p_m = secure_mermaid(blk["code"])
        if new_ != blk["code"]:
            blk["code"] = new_
            log_ += [f"{path_txt}: {x}" for x in p_m]
    if type_ == "formula" and isinstance(blk.get("latex"), str):
        display = blk.get("display") == "block"
        html, stage = formel_html(blk["latex"], display=display)
        if blk.get("html") != html:
            blk["html"] = html
            log_.append(f"{path_txt}: formula -> {stage}")
    for path_ in FIELDS_HTML.get(type_, []):
        if (type_, path_[0]) in FIELDS_TABOO:
            continue
        _set(blk, path_, normalise_html_field, log_, path_txt)
    for path_ in FIELDS_TEXT.get(type_, []):
        if (type_, path_[0]) in FIELDS_TABOO:
            continue
        _set(blk, path_, normalise_text_field, log_, path_txt)
    # Two-level nesting: quiz.questions[].options[].text/.feedback. `_set`
    # knows only one level — so exactly these fields would stay untreated,
    # although `shell.html` sends them through `esc()` and HTML appears there
    # literally ("<p>A) Ja, weil …</p>" in an answer option).
    if type_ == "quiz":
        for fi, question in enumerate(blk.get("questions") or []):
            if not isinstance(question, dict):
                continue
            for oi, opt in enumerate(question.get("options") or []):
                if not isinstance(opt, dict):
                    continue
                for field_ in ("text", "feedback"):
                    if isinstance(opt.get(field_), str):
                        new_value, p = normalise_text_field(opt[field_])
                        if new_value != opt[field_]:
                            opt[field_] = new_value
                            log_ += [f"{path_txt}.questions[{fi}].options[{oi}]"
                                     f".{field_}: {x}" for x in p]
    return log_


def normalise_lesson(lesson: dict) -> list[str]:
    log_: list[str] = []
    if isinstance(lesson.get("title"), str):
        new_, p = normalise_text_field(lesson["title"])
        if new_ != lesson["title"]:
            lesson["title"] = new_
            log_ += [f"lektion({lesson.get('id')}).titel: {x}" for x in p]
    for i, blk in enumerate(lesson.get("blocks") or []):
        log_ += normalise_block(blk, f"lektion({lesson.get('id')}).blocks[{i}]")
    return log_


def normalise_unit(unit: dict) -> list[str]:
    """Normalises a complete unit in place. Returns a log."""
    log_: list[str] = []
    for l in unit.get("lessons") or []:
        log_ += normalise_lesson(l)
    for m in unit.get("modules") or []:
        for i, blk in enumerate(m.get("exercises") or []):
            log_ += normalise_block(blk, f"module({m.get('title')}).exercises[{i}]")
    for i, blk in enumerate(unit.get("final_test") or []):
        log_ += normalise_block(blk, f"final_test[{i}]")
    for g in unit.get("glossary") or []:
        if isinstance(g.get("definition"), str):
            new_, p = normalise_text_field(g["definition"])
            if new_ != g["definition"]:
                g["definition"] = new_
                log_ += [f"glossar({g.get('term')}): {x}" for x in p]
    return log_


def normalise_script(html: str) -> tuple[str, list[str]]:
    """Normalises a chapter script (raw text of the script phase)."""
    return normalise_html_field(html)


# ── Mermaid: secure node labels ─────────────────────────────────────────
# The most frequent syntax error in generated diagrams: round brackets (or
# other shape characters) in an unquoted label — `B[Druck (Zugspannung)]`.
# Mermaid reads `(` as the start of another node shape and stops. Quotation
# marks solve that completely and are always allowed.
_RISKY = re.compile(r"[()\[\]{}<>|#;]")
# An ID followed by a pair of shape brackets. The inner characters are read
# non-greedily up to the matching closing bracket at the end of the line or
# before an edge operator.
# Shape bracket pairs, longest opening first. The closing bracket MUST match
# the opening — a shared alternation would take `)]` as the end in
# `[Text (Klammer)]` and swallow the round bracket.
#
# Completeness is not optional here: a missing shape would be caught by the
# simple pattern and DESTROYED. Every stadium element `A([Start])` would
# become `A("[Start]")`, a rounded box with visible square brackets, in every
# diagram of every unit.
_PAIRS = [("(((", ")))"), ("[[", "]]"), ("[(", ")]"), ("([", "])"),
          ("((", "))"), ("{{", "}}"),
          ("[/", "/]"), ("[/", '\\' + "]"), ("[" + '\\', '\\' + "]"),
          ("[" + '\\', "/]"),
          ("[", "]"), ("(", ")"), ("{", "}"), (">", "]")]

# An opening must not trigger if a LONGER opening begins with the same
# characters: otherwise the shorter pattern applies again after the correct
# pass of the longer one and destroys the node shape. The block is derived
# from the list of pairs instead of being maintained by hand — otherwise it
# would be forgotten with the next new shape pair.
_ALL_OPENERS = {opening for opening, _ in _PAIRS}


def _opening(opening: str) -> str:
    successor = {longer[len(opening)] for longer in _ALL_OPENERS
              if len(longer) > len(opening) and longer.startswith(opening)}
    lock = (f"(?![{re.escape(''.join(sorted(successor)))}])" if successor else "")
    return re.escape(opening) + lock


_NODES = [
    (re.compile(rf"(?P<id>\b[A-Za-z_][\w-]*)"
                rf"(?P<open>{_opening(opening)})"
                rf"(?P<text>[^\n]*?)"
                rf"(?P<close>{re.escape(to)})"
                rf"(?=\s*($|-{{2,}}|={{2,}}|-\.|;|&|:::|~~))"), opening, to)
    for opening, to in _PAIRS]


# In Mermaid edge labels ALWAYS come directly after an arrow: `-->|text|`,
# `---|text|`, `-.->|text|`, `==>|text|`. A pattern matching EVERY pair of
# pipes in the line would also hit pipes INSIDE a node label that has just
# been quoted correctly: `A["p = P(Daten | H0) und nicht P(H0 | Daten)"]` would
# be mangled into `P("Daten |" H0)…` on every repair attempt, and a central
# visual of the unit would end up downgraded. Pipes in quoted labels are
# legal according to the grammar.
# Quoted labels with INNER quotation marks are a mix of quotes
# ('["Große Studie<br/>n>"200 … mittel\'"]'). Some Mermaid 11.x versions
# tolerate them, others do not ('got STR'). The pre-pass resolves them in a
# version-independent way: ONE pair of quotes outside, only apostrophes
# inside. Non-greedy up to the first quotation mark BEFORE a closing bracket,
# so that several nodes per line stay separate.
_QUOTLABEL = re.compile(r'("(?P<mitte>[^\n]*?)")(?=\s*(?:\]|\)|\}))')

_EDGE_LABEL = re.compile(r"(?<=[->=.])\|([^|\n]+)\|")


def _open_bracket(line: str) -> bool:
    """Does a label bracket stay open at the end of the line? (quotes excepted)"""
    without_quote = re.sub(r'"[^"]*"', "", line)
    return any(without_quote.count(opening) > without_quote.count(to)
               for opening, to in (("[", "]"), ("(", ")"), ("{", "}")))


# Whether indentation carries structure is known to the type registry —
# otherwise this list would have to be maintained with every new type.
from src.unit import diagram_types as _dtype
# Keywords that confuse the parser as an INDEPENDENT word in a label. Word
# boundaries are decisive: "Ende" and "Graphik" are harmless, a standalone
# "end" or "graph" is not.
_MERMAID_KEYWORDS = ("graph", "flowchart", "sequenceDiagram", "gantt", "mindmap",
                     "classDiagram", "stateDiagram", "erDiagram", "subgraph", "end")
_DIAGRAM_START = re.compile(
    r"^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(-v2)?|"
    r"erDiagram|journey|gantt|pie|quadrantChart|requirementDiagram|gitGraph|"
    r"mindmap|timeline|sankey-beta|xychart-beta|block-beta|packet-beta|"
    r"architecture-beta|radar-beta|kanban|treemap)\b", re.I)


def _first_diagram_only(code: str) -> tuple[str, list[str]]:
    """Keeps only the first diagram if several are chained together.

    Checked only at the start of a line — a label may contain words such as
    "Timeline" or "Journey" without triggering a cut.
    """
    rows = code.splitlines()
    starts = [i for i, raw in enumerate(rows)
              if (z := raw.strip()) and not z.startswith("%%")
              and not z.lower().startswith(("subgraph", "end"))
              and _DIAGRAM_START.match(z)]
    if len(starts) > 1:
        return "\n".join(rows[starts[0]:starts[1]]), [
            f"Mermaid: {len(starts)} diagrams in one block — only the first kept"]
    return code, []


def _defuse_label(text: str) -> str:
    """Removes Mermaid keywords as independent words from labels."""
    for kw in _MERMAID_KEYWORDS:
        text = re.sub(rf"\b{re.escape(kw)}\b", "", text)
    return " ".join(text.split())


# Unicode sub/superscripts that the Mermaid lexer does NOT accept — neither
# unquoted (NON_ESCAPED_TEXT breaks) nor in quotation marks (ESCAPED_TEXT
# breaks as well). Reproduced: a Sankey diagram failed on "H₀" alone ("Parse
# error on line 2 … got 'NON_ESCAPED_TEXT'"); with "H0" the same code parses.
# Quoting demonstrably does not help — the characters must be mapped to ASCII.
_UNI_SUBSUP = str.maketrans({
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "₊": "+", "₋": "-", "₌": "=", "₍": "(", "₎": ")",
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁺": "+", "⁻": "-", "⁼": "=", "⁽": "(", "⁾": ")",
    "ⁿ": "n", "ᵢ": "i", "ₐ": "a", "ₑ": "e", "ₒ": "o",
    "ₓ": "x", "ₖ": "k", "ₘ": "m", "ₙ": "n", "ₚ": "p", "ₛ": "s", "ₜ": "t",
})


def mermaid_subsup_to_ascii(code: str) -> tuple[str, list[str]]:
    """Maps sub/superscript characters in Mermaid code to ASCII."""
    new_ = (code or "").translate(_UNI_SUBSUP)
    if new_ != code:
        return new_, ["Mermaid: Unicode sub/superscripts replaced by ASCII (the parser does not accept them, even when quoted)"]
    return code, []



_SANKEY_TRANSLIT = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe",
                    "Ü": "Ue", "ß": "ss", "≥": ">=", "≤": "<=", "–": "-",
                    "—": "-", "„": "'", "“": "'", "”": "'", "…": "..."}


def _sankey_ascii(code: str, log_: list) -> str:
    """The sankey-beta lexer accepts NO non-ASCII characters — neither quoted
    nor unquoted (bisected empirically: 'ausgewählt' breaks in every form,
    the ASCII variant parses; the same class as the H₀ subscript, only
    broader). For German content that means: without transliteration
    practically every Sankey would be downgraded. Umlauts are written out by
    German convention (ae/oe/ue/ss), the rest is defused by NFKD; whatever is
    not ASCII after that is dropped.
    """
    if code.isascii():
        return code
    new_ = code
    for from_, to in _SANKEY_TRANSLIT.items():
        new_ = new_.replace(from_, to)
    if not new_.isascii():
        new_ = unicodedata.normalize("NFKD", new_)
        new_ = "".join(c for c in new_ if not unicodedata.combining(c))
        new_ = "".join(c if c.isascii() else "" for c in new_)
    log_.append("Sankey: non-ASCII characters transliterated (the sankey lexer accepts ASCII only, even when quoted)")
    return new_


_QUADRANT_LABEL_LINE = re.compile(r"^(\s*(?:title|x-axis|y-axis|quadrant-[1-4])\b[^:\n]*):\s*",
                                  re.MULTILINE)


def _secure_quadrant(code: str, log_: list) -> str:
    """Replaces colons in quadrantChart LABEL LINES in a version-independent way.

    Example: 'quadrant-1 Konfirmatorisch, hohe Kosten: FWER (Bonferroni)'
    parses in Mermaid 11.14, but other 11.x versions reject the colon (got
    'COLON' — the token list of the error knows no COLON there). Replacement
    happens only in title/x-axis/y-axis/quadrant-N lines — in POINT LINES
    ('"Label": [x, y]') the colon is syntax and stays.
    """
    new_, n = _QUADRANT_LABEL_LINE.subn(r"\1 – ", code)
    if n:
        log_.append(f"quadrantChart: {n} colon(s) in label lines replaced (not accepted in some versions)")
    return new_


_SANKEY_ARROW = re.compile(r"^(.*?)\s*[-=]{2,}>\s*(.*?)\s*:\s*([\d.,]+\s*%?)\s*$")
_SANKEY_NUMBER = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*%?\s*$")


def _secure_sankey(code: str, log_: list) -> str:
    """Repairs the empirically proven Sankey error classes deterministically.

    Determined against the real Mermaid grammar: parse errors are caused by
    exactly (a) decimal commas in the value ('…,47,5' — four fields), (b)
    unquoted commas in node names ('Signifikant, aber klein,…') and (c) arrow
    syntax in flowchart style ('A --> B: 80'). Unit words, percent signs,
    thousands separators and a missing '-beta' parse, on the other hand.
    Without this repair a Sankey that carries the central visual of a unit
    would end up downgraded, because the repair loop cannot close such lines
    mechanically.

    Commas in labels are only resolved if the assignment is UNAMBIGUOUS (the
    combined name occurs in a well-formed line of the same diagram) —
    otherwise the line is left to the model repair run.
    """
    rows = code.splitlines()
    data_ = [z for z in rows[1:] if z.strip() and not z.strip().startswith("%%")]
    # Node names from well-formed lines (exactly 3 fields, without quotes):
    known = set()
    for z in data_:
        if '"' in z:
            continue
        f = [t.strip() for t in z.split(",")]
        if len(f) == 3 and _SANKEY_NUMBER.match(f[2]):
            known.update(f[:2])

    def _value(w: str) -> str:
        return w.strip().replace(",", ".")

    new_ = [rows[0]]
    for z in rows[1:]:
        raw = z.strip()
        if not raw or raw.startswith("%%") or '"' in raw:
            new_.append(z)
            continue
        m = _SANKEY_ARROW.match(raw)
        if m:
            q, target = m.group(1).strip(), m.group(2).strip()
            q = f'"{q}"' if "," in q else q
            target = f'"{target}"' if "," in target else target
            new_.append(f"{q},{target},{_value(m.group(3))}")
            log_.append(f"Sankey: Pfeil-Syntax in CSV-Zeile umgeschrieben ({raw[:40]})")
            continue
        f = [t.strip() for t in raw.split(",")]
        if len(f) <= 3:
            new_.append(z)
            continue
        # (a) decimal comma in the value: '…,47,5' -> '…,47.5'
        if len(f) == 4 and f[2].isdigit() and _SANKEY_NUMBER.match(f[3]):
            new_.append(f"{f[0]},{f[1]},{f[2]}.{f[3].rstrip('%').strip()}"
                       + ("%" if f[3].strip().endswith("%") else ""))
            log_.append(f"Sankey: decimal comma in a value repaired ({raw[:40]})")
            continue
        # (b) Comma in the node name: resolve unambiguously through known
        # nodes.
        labels, value = f[:-1], f[-1]
        if _SANKEY_NUMBER.match(value):
            for i in range(1, len(labels)):
                source = ", ".join(labels[:i])
                target = ", ".join(labels[i:])
                if source in known or target in known:
                    q = f'"{source}"' if "," in source else source
                    t = f'"{target}"' if "," in target else target
                    new_.append(f"{q},{t},{_value(value)}")
                    log_.append(f"Sankey: node names with a comma quoted ({raw[:40]})")
                    break
            else:
                new_.append(z)          # ambiguous -> repair loop
        else:
            new_.append(z)
    return "\n".join(new_)


def secure_mermaid(code: str) -> tuple[str, list[str]]:
    """Puts node and edge labels in quotation marks where needed."""
    log_: list[str] = []
    code, log_u = mermaid_subsup_to_ascii(code or "")
    log_ += log_u

    def _node(m):
        # No pattern may strike INSIDE a quoted label: the odd-shape form
        # `id>label]` would otherwise match the `n>` in `["…n>'200…"]` and take
        # the just repaired label apart again — the same class as the edge
        # label case above. If an ODD number of quotation marks precedes the
        # hit, it lies in an open string.
        if m.string.count('"', 0, m.start()) % 2 == 1:
            return m.group(0)
        text = m.group("text").strip()
        if not text:
            return m.group(0)
        if text.startswith('"'):
            return m.group(0)
        # Even a label without special characters can break if a Mermaid
        # keyword stands in it as an independent word.
        if not _RISKY.search(text) and _defuse_label(text) == text:
            return m.group(0)
        clean = _defuse_label(text.replace('"', "'"))
        if clean != text:
            log_.append(f"Mermaid keyword removed from label: {text[:40]}")
        log_.append(f"Mermaid label quoted: {clean[:40]}")
        return m.group("id") + m.group("open") + '"' + (clean or m.group("id")) + '"' + m.group("close")

    def _edge(m):
        text = m.group(1).strip()
        if not text or text.startswith('"') or not _RISKY.search(text):
            return m.group(0)
        log_.append(f"Mermaid edge label quoted: {text[:40]}")
        return '|"' + text.replace('"', "'") + '"|'

    code, log_e = _first_diagram_only(code or "")
    log_ += log_e

    # Merging labels and quoting node and edge labels are FLOWCHART grammar.
    # Applied to other types they destroy the code: in erDiagram `{` and `|`
    # are STRUCTURE (cardinality `||--o{`, attribute blocks `ENTITY { … }`) —
    # merging brackets would fuse the whole diagram into one line and a node
    # pattern would quote across it. For non-flow types only the type-neutral
    # steps remain (Unicode to ASCII, first diagram, clean-up).
    type_ = _dtype.detect(code)
    if type_ not in ("flowchart", "graph"):
        if type_ == "sankey-beta":
            code = _sankey_ascii(_secure_sankey(code, log_), log_)
        elif type_ == "quadrantChart":
            code = _secure_quadrant(code, log_)
        carries = _dtype.indentation_matters(code)
        clean = []
        for z in code.splitlines():
            if not z.strip():
                continue
            if carries:
                depth = len(z) - len(z.lstrip())
                clean.append(" " * depth + " ".join(z.split()))
            else:
                clean.append(" ".join(z.split()))
        return "\n".join(clean), log_

    # Pre-pass: merge labels that run over a real line break again. Models like
    # to write
    #     C --> D[Cortex
    #     (Apoplast/Symplast)]
    # That is invalid in Mermaid — the line break ends the statement, and the
    # continuation is read as a new statement ("got 'PS'"). The line break
    # becomes <br/>, which Mermaid knows as a break inside a label.
    raw = (code or "").splitlines()
    together: list[str] = []
    for line in raw:
        if together and _open_bracket(together[-1]):
            together[-1] = together[-1].rstrip() + "<br/>" + line.strip()
            log_.append("Mermaid: umgebrochenes Label zusammengefuehrt")
        else:
            together.append(line)

    rows = []
    for line in together:
        # subgraph titles need the same protection as node labels:
        #   subgraph ID [Titel (Zusatz)]
        # breaks with "Expecting … got 'PS'", because Mermaid reads the round
        # bracket as the start of a node shape. The general node expression
        # does not apply here, because the keyword, not a node identifier,
        # precedes the bracket.
        m_sub = re.match(r"(\s*subgraph\s+\S+\s*)\[([^\n]*)\](\s*)$", line)
        if m_sub:
            title = m_sub.group(2).strip()
            if title and not title.startswith('"') and _RISKY.search(title):
                log_.append(f"Mermaid subgraph title quoted: {title[:40]}")
                line = (m_sub.group(1) + '["' + title.replace('"', "'") + '"]'
                         + m_sub.group(3))
            rows.append(line)
            continue
        # do not touch style/classDef/click directives
        if re.match(r"\s*(style|classDef|class|click|linkStyle|subgraph|end)\b", line):
            rows.append(line)
            continue
        def _inner(m):
            middle = m.group("mitte")
            if '"' not in middle:
                return m.group(0)
            log_.append(f"Mermaid: inner quotation marks in label replaced ({middle[:40]})")
            return '"' + middle.replace('"', "'") + '"'
        line = _QUOTLABEL.sub(_inner, line)
        for pattern, _auf, _to in _NODES:
            line = pattern.sub(_node, line)
        rows.append(_EDGE_LABEL.sub(_edge, line))

    # Remove blank lines and double spaces. In mindmap, timeline, kanban and
    # treemap the indentation carries the hierarchy and is kept.
    carries = _dtype.indentation_matters("\n".join(rows))
    clean = []
    for z in rows:
        if not z.strip():
            continue
        if carries:
            depth = len(z) - len(z.lstrip())
            clean.append(" " * depth + " ".join(z.split()))
        else:
            clean.append(" ".join(z.split()))
    return "\n".join(clean), log_
