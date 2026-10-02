# -*- coding: utf-8 -*-
"""Registry of the usable Mermaid diagram types.

One single source for three consumers that would otherwise drift apart:

  * `prompts/learning.py` — which type fits which LEARNING PURPOSE, with
    scaffold
  * `unit/normalization.py` — whether indentation carries meaning
  * `unit/validator.py` — whether the type is known and the structure holds

The selection rule is deliberately didactic rather than formal: a diagram
is worth it if it makes visible a relation the reader would otherwise have
to keep in their head. Which relation that is decides the type.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.i18n import N_


@dataclass(frozen=True)
class DiagramType:
    key: str                  # Mermaid start word, as it appears in the code
    purpose: str                       # which relation becomes visible (choice of type)
    didactics: str                    # which LEARNING ACTIVITY the diagram enables
    not_when: str                   # most frequent misuse
    degrees_of_freedom: str              # what can be varied (for generation)
    scaffold: str                     # minimal, valid example
    indentation_matters: bool = False  # indentation is structure, not cosmetics
    pattern: tuple[str, ...] = ()      # structure check: at least one must match
    shortcoming: str = ""                  # message if no pattern matches
    aliases: tuple[str, ...] = field(default_factory=tuple)


TYPES: dict[str, DiagramType] = {t.key: t for t in (
    DiagramType(
        "flowchart",
        "Process with branching: what happens in which order, "
        "and where is the further path decided?",
        "The learner can trace a concrete case through the diagram "
        "— \"follow the path for case X\". Every "
        "branch is a possible quiz question, because a "
        "decision is made there.",
        "Not for mere enumerations without order — a list is "
        "enough for that.",
        "Node shapes carry meaning: [rectangle] step, {diamond} "
        "decision, ([stadium]) start/end, [(cylinder)] storage, "
        "[/parallelogram/] input and output. Label edges with "
        "-->|condition|, side paths dashed with -.->, "
        "responsibilities via one subgraph per lane, direction LR or TD.",
        "flowchart LR\n  A([Start]) --> B{Condition}\n  B -->|yes| C[Path 1]\n  B -->|no| D[Path 2]",
        pattern=(r"-->", r"---", r"-\.->"),
        shortcoming=N_("no edge — a flowchart without connections only shows boxes"),
        aliases=("graph",)),

    DiagramType(
        "stateDiagram-v2",
        "States and transitions: something IS in a state, and "
        "events change it. The central form for control loops and "
        "controllers.",
        "Allows the question \"which state is the system in after "
        "A, then B?\" — that checks understanding rather than memorisation. "
        "Makes visible that a state STAYS until an event "
        "occurs; exactly that is what learners overlook in control loops.",
        "Not for work steps that are run through once — that "
        "is a process.",
        "[*] marks beginning and end. Label transitions with the triggering "
        "event (A --> B: stimulus rises). Nested "
        "states for sub-processes, note right of X for explanations, "
        "<<choice>> for conditions, -- for concurrent regions.",
        "stateDiagram-v2\n  [*] --> Closed\n  Closed --> Open: stimulus rises\n  Open --> Closed: stimulus falls",
        pattern=(r"-->",),
        shortcoming=N_("no transition — a state diagram without transitions shows nothing"),
        aliases=("stateDiagram",)),

    DiagramType(
        "sequenceDiagram",
        "Exchange between participants over time: who reports what "
        "to whom, in which order, and who waits for what?",
        "Shows order AND waiting relations. The learner sees "
        "who waits for whom and where a process gets stuck — "
        "the basis for error analysis tasks.",
        "Not for processes without several participants.",
        "->> synchronous, -) asynchronous, -->> reply. activate and "
        "deactivate show the processing time as a bar. alt/else "
        "for case distinction, opt for optional parts, loop for "
        "repetition, Note over A,B for explanations.",
        "sequenceDiagram\n  Provider->>Authority: application\n  activate Authority\n  Authority-->>Provider: decision\n  deactivate Authority",
        pattern=(r"->>", r"-->>", r"->", r"--\)"),
        shortcoming=N_("no message between participants")),

    DiagramType(
        "timeline",
        "Chronology: what happened when, and how do the periods "
        "relate? Makes development over time visible as a whole.",
        "Makes simultaneity visible: what ran in parallel, what followed "
        "on what? Allows placement tasks — \"where does "
        "this event belong?\".",
        "Not for processes without reference to time.",
        "section groups epochs. Several events per point in time "
        "through further colons (1900 : first : second). "
        "Points in time may be numbers, years or names of phases.",
        "timeline\n  title Development\n  section Early phase\n    1850 : First observation\n    1900 : Theory : Counter-thesis",
        indentation_matters=True,
        pattern=(r":",),
        shortcoming=N_("no entry in the format 'point in time : event'")),

    DiagramType(
        "mindmap",
        "Map of terms as a PREVIEW: what belongs to the topic, "
        "and how is it organised?",
        "As a preview it activates prior knowledge and shows the scope "
        "before going into detail — the learner knows where they "
        "are. At the end of a chapter it achieves little, because it has no "
        "direction.",
        "Not for processes or cause and effect — a mind map has "
        "no direction.",
        "Root shapes: ((round)), [square], ))cloud((, {{hexagon}}. "
        "Any depth through indentation in steps of two. The "
        "indentation IS the structure — no arrows, no order.",
        "mindmap\n  root((Topic))\n    Area A\n      Detail\n    Area B",
        indentation_matters=True,
        pattern=(r"^\s*\w",),
        shortcoming=N_("no branches below the root")),

    DiagramType(
        "pie",
        "Shares of a whole: how is a quantity distributed, and what "
        "dominates? Only meaningful if the parts add up to a "
        "whole.",
        "Proportions become graspable at once, without calculating. "
        "Suitable for an estimation question before revealing: \"which "
        "share is the largest?\".",
        "Not for comparing independent quantities — use a "
        "bar chart as chart for that.",
        "showData shows the numbers. The title is on the same "
        "line (pie title …). Labels belong in "
        "quotation marks. Sensible up to about six segments — beyond that "
        "it becomes unreadable.",
        "pie showData title Distribution\n  \"Share A\" : 60\n  \"Share B\" : 40",
        pattern=(r'"[^"]+"\s*:\s*[\d.]+',),
        shortcoming=N_("no entry in the format \"label\" : number")),

    DiagramType(
        "quadrantChart",
        "Placement along two dimensions: what lies where when two "
        "criteria are applied at the same time?",
        "Makes classification tangible as an area rather than a list. The "
        "learner can place new cases themselves — an exercise "
        "arises directly from the display.",
        "Not when only one dimension counts — a ranking is "
        "enough then.",
        "Name x-axis and y-axis with both poles (Low --> High). "
        "quadrant-1 to quadrant-4 name the fields by content. "
        "Points as name: [x, y] with values between 0 and 1.",
        "quadrantChart\n  title Placement\n  x-axis Low --> High\n  y-axis Low --> High\n  quadrant-1 Priority\n  Case A: [0.3, 0.7]",
        pattern=(r"\[\s*[\d.]+\s*,\s*[\d.]+\s*\]",),
        shortcoming=N_("no placed point in the format 'name: [x, y]'")),

    DiagramType(
        "sankey-beta",
        "Flows of quantities with losses: where does how much go, and where is "
        "something lost on the way? The form for balances and "
        "budgets.",
        "Losses and shares become proportionally visible — the question "
        "\"where does most of it go?\" answers itself visually. "
        "Suitable where input and use diverge.",
        "Not for processes without quantities.",
        "Every line is source,target,quantity. Any number of "
        "intermediate nodes: a node can be the target of one line and the source of the "
        "next. The width of the bars follows from the "
        "quantities — they must fit together. Node names ASCII ONLY: "
        "write umlauts as ae/oe/ue/ss, no special characters — "
        "the sankey lexer does not accept them, not even in "
        "quotation marks.",
        "sankey-beta\n  Intake,Use,30\n  Intake,Loss,70",
        pattern=(r"^[^,\n]+,[^,\n]+,\s*[\d.]+\s*$",),
        shortcoming=N_("no line in the format 'source,target,quantity'")),

    DiagramType(
        "erDiagram",
        "Entities and their relations: what is connected with what, and "
        "with which multiplicity?",
        "Makes multiplicities explicit: \"one, but many of those\" is "
        "usually the actual insight. Allows check questions on "
        "cardinalities.",
        "Not for processes — an ER diagram has no order.",
        "Cardinalities left and right: || exactly one, o| zero or "
        "one, }| one or more, o{ zero or more. Name the relation "
        "with : operates. Attributes in the block of the entity, with type and "
        "name.",
        "erDiagram\n  PROVIDER ||--o{ SYSTEM : operates\n  SYSTEM {\n    string identifier\n  }",
        pattern=(r"\|\|--", r"\}o--", r"--o\{", r"--\|\{"),
        shortcoming=N_("no relation between entities")),

    DiagramType(
        "classDiagram",
        "Structure with features: which types are there, what "
        "characterises them, and how do they relate to each other?",
        "Shows what types have in common and where they "
        "differ — the basis for matching tasks and for the "
        "question \"what inherits from what?\".",
        "Not for pure hierarchies without features — a "
        "flowchart TD is enough for that.",
        "Features and behaviour in the class block, + public and - "
        "private. Relations: <|-- inheritance, *-- composition, o-- "
        "aggregation, --> use. Label with : after the "
        "relation.",
        "classDiagram\n  class Vessel {\n    +diameter\n  }\n  Vessel <|-- Tracheid : special form",
        pattern=(r"<\|--", r"\*--", r"o--", r"-->", r"class\s+\w+"),
        shortcoming=N_("no class and no relation")),

    DiagramType(
        "journey",
        "Experience path with ratings: how does someone experience a process "
        "step by step, and where does it get difficult?",
        "Makes experience ratable and shows where a process becomes difficult "
        "for those affected. Starting point for "
        "improvement tasks: \"which step should be eased?\".",
        "Not for technical processes without a person involved.",
        "section structures phases. Per step a rating from 1 "
        "(bad) to 5 (good) and the roles involved, "
        "comma-separated. Several roles can experience the same step "
        "differently.",
        "journey\n  title Process\n  section Preparation\n    Submit application: 3: Provider, Authority",
        indentation_matters=True,
        pattern=(r":\s*\d",),
        shortcoming=N_("no step with a rating in the format 'step: score: role'")),

    DiagramType(
        "gantt",
        "Projects with durations and overlaps: what runs when, what "
        "in parallel, what depends on what?",
        "Shows parallelism and dependencies. The question \"what "
        "is delayed if X comes later?\" becomes answerable — a "
        "prediction task arises directly.",
        "Not for processes without duration.",
        "section structures parts. Dependency via after id. "
        "milestone for points in time without duration, crit for the critical "
        "path. dateFormat sets the date pattern; durations as 30d "
        "or 2w.",
        "gantt\n  title Process\n  dateFormat YYYY-MM-DD\n  section Phase\n  Step A :a1, 2024-01-01, 30d\n  Step B :after a1, 14d",
        indentation_matters=True,
        pattern=(r":\s*\w*,?\s*\d{4}-\d{2}-\d{2}", r"\d+[dw]\b", r"after\s+\w+"),
        shortcoming=N_("no task with a date or duration")),

)}


# alias -> canonical key
_ALIAS = {a: t.key for t in TYPES.values() for a in t.aliases}
_START = re.compile(r"^\s*([A-Za-z][\w-]*)", re.M)


def detect(code: str) -> str | None:
    """Determines the diagram type from the source."""
    m = _START.search(code or "")
    if not m:
        return None
    word = m.group(1)
    if word in TYPES:
        return word
    if word in _ALIAS:
        return _ALIAS[word]
    # tolerate upper/lower case
    small = {k.lower(): k for k in TYPES}
    return small.get(word.lower()) or _ALIAS.get(word.lower())


def indentation_matters(code: str) -> bool:
    type_ = detect(code)
    return bool(type_ and TYPES[type_].indentation_matters)


def structure_finding(code: str) -> str | None:
    """Checks the minimal structure. Returns None = fine.

    Catches the cases that pass the syntax probe but give the learner an
    empty or meaningless picture — a flowchart without edges, for
    instance.
    """
    type_ = detect(code)
    if type_ is None:
        return None
    spec = TYPES[type_]
    if not spec.pattern:
        return None
    body = "\n".join(z for z in (code or "").splitlines()[1:] if z.strip())
    if any(re.search(p, body, re.M) for p in spec.pattern):
        return None
    return spec.shortcoming


def prompt_catalog_short() -> str:
    """List of purposes without syntax — for PLANNING.

    The detail plan decides which diagram goes where, but writes no syntax.
    With the scaffolds the prompt would only grow — and without the purposes
    it picks flowchart by reflex.
    """
    rows = ["DIAGRAM TYPES — NAME the type in the media plan, e.g.",
            "\"diagram:stateDiagram-v2 (control loop of the opening)\".",
            "The choice follows the learning purpose:", ""]
    for t in TYPES.values():
        rows.append(f"  {t.key}")
        rows.append(f"      Shows:   {t.purpose}")
        rows.append(f"      Use:     {t.didactics}")
        rows.append(f"      Not:     {t.not_when}")
        rows.append("")
    rows += ["", "Without a type, a flowchart arises by reflex — even where a",
             "state diagram, a timeline or a balance would show the matter better."]
    return "\n".join(rows)


def prompt_catalog() -> str:
    """Complete catalogue with syntax scaffold — for GENERATION."""
    rows = ["MERMAID DIAGRAM TYPES — choose by the LEARNING PURPOSE, not by habit.",
            "A diagram is worth it if it makes visible a relation the",
            "reader would otherwise have to keep in their head.", ""]
    for t in TYPES.values():
        rows.append(f"* {t.key} — {t.purpose}")
        rows.append(f"    Didactic use: {t.didactics}")
        rows.append(f"    Do not use: {t.not_when}")
        rows.append(f"    Degrees of freedom: {t.degrees_of_freedom}")
        rows.append("    Scaffold:")
        rows.append("      " + t.scaffold.replace("\n", "\n      "))
        rows.append("")
    rows.append("A unit that knows only flowchart gives away expressive power.")
    return "\n".join(rows)
