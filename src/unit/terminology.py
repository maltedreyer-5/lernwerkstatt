# -*- coding: utf-8 -*-
"""Terminology control: prevents models from coining their own technical terms.

The problem: if `_harvest_glossary` and `new_terms` took EVERY newly
appearing term into the glossary and `cross_prompt` turned it into the
"binding terminology" for the next chapter, a coinage from chapter 2 would
become the standard for chapters 3 to 8 — the system would stabilise its own
inventions.

Two classes are therefore kept apart:

  FIXED      concept inventory, terms from the uploaded material, optionally a
             curated domain glossary. Only this class goes into the prompts
             as binding.
  CANDIDATE  newly appeared. Collected, checked, and fixed only after approval
             (or evidence).

The check has several stages, cheap ones first: whitelist, then source
corpus, then compound splitting. Only the rest goes to a model.

On compound splitting: "Risikomanagementsystem" is in no dictionary and is
nevertheless perfectly legitimate German. A plain lexicon comparison would
therefore produce a flood of false alarms. Words are split against the
vocabulary that is known from inventory and sources anyway: if all
components are covered, the compound counts as covered.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Minimum length of a candidate (single words). Short words are almost never
# coinages and only produce noise. Without this limit the pronoun "Sie" can
# become a candidate, be answered by the model with the meta description
# "Personalpronomen (kein Fachterminus)", and that description then be written
# into every sentence of the chapter scripts by regex. It applies in
# `_check_one` and `replace` (the latter also protects against old, persisted
# blocklists).
MIN_LENGTH = 9

# Words that must NEVER be a term candidate or a replacement source:
# pronouns, demonstratives, forms of address, number and quantity words.
# Otherwise the DEFINITION_PATTERN matches sentence beginnings such as "Sie
# bezeichnet …" or "Dieser Ausdruck beschreibt …".
FUNCTION_WORDS = {
    "sie", "er", "es", "ich", "wir", "ihr", "man", "wer", "was",
    "dieser", "diese", "dieses", "diesen", "diesem", "jener", "jene",
    "jenes", "jenen", "jenem", "solche", "solcher", "solches", "solchen",
    "welche", "welcher", "welches", "derselbe", "dieselbe", "dasselbe",
    "hier", "dort", "dabei", "damit", "dadurch", "daher", "deshalb",
    "tausend", "tausende", "tausenden", "hundert", "hunderte", "hunderten",
    "million", "millionen", "dutzend", "dutzende", "dutzenden",
    "viele", "vielen", "einige", "einigen", "mehrere", "mehreren",
}

# Markers by which a model "substitute" can be recognised as a meta comment
# instead of an insertable term. Such a thing must NEVER flow into the text or
# the terminology (example: "Personalpronomen (kein Fachterminus)").
# German and English: the prompt is English, but a model writing a German
# unit may answer in either language.
_META_SUBSTITUTES = ("kein fachterminus", "keine ersetzung", "kein terminus",
                     "kein etablierter", "umschrieben als", "vgl.", "bzw. ",
                     "keine neuschoepfung", "nicht ersetzen",
                     "no technical term", "not a technical term", "no replacement",
                     "no established", "paraphrased as", "paraphrase for", "cf.",
                     "no coinage", "do not replace", "not replace", "i.e. ", "e.g. ")
# A substitute must be insertable syntactically at the occurrence — a noun
# phrase, not an explanatory sentence. Anything longer is an explanation.
MAX_SUBSTITUTE_LENGTH = 60


def substitute_usable(term: str, substitute: str) -> bool:
    """Is the model's substitute an insertable term (not a meta explanation)?"""
    e = (substitute or "").strip()
    if not e or len(e) > MAX_SUBSTITUTE_LENGTH:
        return False
    n_e = normal(e)
    if not n_e or n_e == normal(term):
        return False
    small = e.lower()
    if any(m in small for m in _META_SUBSTITUTES):
        return False
    # Explanatory punctuation: a term contains no punctuation except brackets
    # and hyphens.
    if any(z in e for z in (";", ":", "—", "„", "  ")) or e.endswith("."):
        return False
    return True


_ENDINGS = ("en", "er", "es", "em", "e", "n", "s")


# ── Glossary variants ─────────────────────────────────────────────────────
# Models produce glossary variants such as 26 entries for 9 concepts —
# "Benjamini-Hochberg-Verfahren (BH)" next to "… (BH-Verfahren)" and three
# spellings of PRDS. A plain comparison of cores (bracket stripped) would be
# TOO aggressive, though: "q-Wert" and "q-Wert (Storey)" are a GENUINE
# distinction within the same unit, and so are "Anbieter (KI-VO)" and
# "Anbieter (DSGVO)". Hence two separate questions: `glossary_duplicate` merges
# only provable NOTATION VARIANTS (safe without loss), `glossary_suspect` names
# everything that can be confused for a warning — the decision stays with the
# critic or the rework, never with the deduplication.

def core_term(term: str) -> str:
    """The term without the parenthetical addition — the same rule as in covered()."""
    return re.sub(r"\s*\([^)]*\)\s*", " ", term or "").strip()


def _bracket_content(term: str) -> str:
    m = re.search(r"\(([^)]*)\)", term or "")
    return (m.group(1) if m else "").strip()


def abbrev_variant(addition: str, core: str) -> bool:
    """Is `addition` an abbreviation or notation variant of `core`?

    "BH" and "BH-Verfahren" are variants of "Benjamini-Hochberg-Verfahren",
    "FWER" of "Family-Wise Error Rate". "Storey", "Boolesche Ungleichung" or
    "DSGVO" are not — they QUALIFY the term and must never lead to merging.
    """
    z = normal(addition)
    words = [normal(w) for w in re.split(r"[\s\-–—/]+", (core or "").strip()) if w]
    if not z or not words:
        return False
    # Remove complete core words from the addition ("BH-Verfahren" -> "bh") …
    rest = z
    for w in sorted(words, key=len, reverse=True):
        if len(w) >= 4:
            rest = rest.replace(w, "")
    # … the rest must be a prefix of the core's initials. Short words such as
    # "on"/"a" give no initial — abbreviations skip them (PRDS).
    initials = "".join(w[0] for w in words if len(w) >= 3)
    return 2 <= len(rest) <= len(initials) and initials.startswith(rest)


def glossary_duplicate(a: str, b: str) -> bool:
    """Are two glossary terms provably notation variants?"""
    na, nb = normal(a), normal(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ka, kb = core_term(a), core_term(b)
    if not normal(ka) or normal(ka) != normal(kb):
        return False
    for addition in (_bracket_content(a), _bracket_content(b)):
        if addition and not abbrev_variant(addition, ka):
            return False
    return True


def glossary_suspect(a: str, b: str) -> str:
    """Reason for suspecting entries that are close enough to be confused (empty =
    none).

    Calibrated for low noise: the same core is only reported if one side
    stands WITHOUT a parenthetical addition (the typical duplicate form); if
    both sides carry DIFFERENT additions, that is a deliberate
    disambiguation of homonyms and no finding. An identical addition on
    different cores only counts if it is an abbreviation variant of one of
    the cores — otherwise it is a shared qualifier (a statute abbreviation,
    for instance) and perfectly legitimate.
    """
    if glossary_duplicate(a, b):
        return "Notationsvarianten desselben Begriffs"
    ka, kb = core_term(a), core_term(b)
    za, tb = _bracket_content(a), _bracket_content(b)
    if normal(ka) and normal(ka) == normal(kb) and not (za and tb):
        return "same core term, once with and once without a parenthetical addition"
    if (normal(ka) and normal(ka) == normal(tb)) or (normal(kb) and normal(kb) == normal(za)):
        return "the core of one is the parenthetical addition of the other"
    if (za and normal(za) == normal(tb)
            and (abbrev_variant(za, ka) or abbrev_variant(tb, kb))):
        return "same abbreviation as parenthetical addition on different terms"
    return ""


def stem_form(term: str) -> str:
    """Rough stem form per word — merges inflection variants.

    Example: 'positive regressionsabhängigen Struktur' (rejected) and
    'positiven regressionsabhängigen Struktur' (new candidate) differ only in
    an ending IN THE MIDDLE of the phrase; without stemming the normalised key
    keeps them apart, and a candidate stays open for good.

    Stripping is ITERATIVE (at most two rounds): 'Verfahrens' carries a
    genitive s AND the en ending — in a single round nominative ('verfahr') and
    genitive ('verfahren') would stay different, and the merging would never
    apply.
    """
    parts = []
    for word in re.split(r"[\s\-–—/]+", (term or "").strip()):
        n = normal(word)
        for _ in range(2):
            if len(n) <= 5:
                break
            for ending in _ENDINGS:
                if n.endswith(ending) and len(n) - len(ending) >= 4:
                    n = n[:len(n) - len(ending)]
                    break
            else:
                break
        parts.append(n)
    return "".join(parts)
# Linking elements of German compounds.
JOINTS = ("s", "n", "en", "es", "er", "e", "ns")
# Minimum length of a compound component.
MIN_TEIL = 4

# Frequent components of German technical compounds. Without this list the
# splitting would report perfectly legitimate formations such as
# "Risikomanagementsystem" as coinages as soon as the component "System"
# happens not to be in the corpus. Deliberately domain-neutral — the subject
# coverage comes from the inventory and the source corpus, not from this list.
BASE_PARTS = """
system verfahren prozess management analyse bewertung pruefung kontrolle
steuerung fuehrung planung sicherung sicherheit qualitaet risiko daten
information dokument dokumentation bericht protokoll richtlinie vorschrift
norm standard anforderung kriterium kriterien massnahme ziel zweck aufgabe
rolle verantwortung pflicht recht gesetz regel regelung ordnung struktur
modell methode technik werkzeug mittel quelle grundlage basis rahmen bereich
ebene stufe phase schritt punkt teil komponente element einheit gruppe klasse
form groesse wert zahl menge anteil grad stand zustand lage situation fall
beispiel muster vorlage plan konzept entwurf fassung version aenderung
anpassung entwicklung umsetzung durchfuehrung einfuehrung betrieb nutzung
anwendung einsatz wirkung folge ergebnis erfolg fehler mangel abweichung
stoerung ausfall schaden gefahr bedrohung schwachstelle luecke schutz abwehr
vorsorge vermeidung minderung behandlung loesung antwort reaktion
entscheidung wahl auswahl anbieter betreiber nutzer anwender behoerde stelle
organisation unternehmen abteilung person mitarbeiter kunde partner lieferant
intelligenz lernen training netz algorithmus software hardware schnittstelle
speicher rechner server dienst leistung produkt markt kosten aufwand nutzen
zeit dauer frist termin zyklus durchlauf inhalt umfang zugriff freigabe
pruefer nachweis beleg beweis erklaerung begruendung bedingung voraussetzung
folgerung schluss uebersicht liste katalog register verzeichnis archiv
""".split()
STOP = {
    "abschnitt", "abbildung", "allerdings", "anwendung", "task", "output",
    "bedeutung", "beispiel", "bereich", "description", "bestandteil",
    "betrachtung", "bewertung", "beziehung", "display", "eigenschaft",
    "introduction", "unit", "entscheidung", "entwicklung", "ergebnis",
    "explanation", "erlaeuterung", "fallbeispiel", "folgende", "question",
    "gegensatz", "gelegenheit", "grundlage", "handlung", "note",
    "information", "chapters", "lesson", "loesung", "moeglichkeit",
    "neuerung", "problem", "reihenfolge", "sachverhalt", "situation",
    "uebersicht", "umsetzung", "unterschied", "ursache", "verfahren",
    "vergleich", "voraussetzung", "summary", "zusammenhang",
}


def normal(w: str) -> str:
    """Comparison form: lower case, without umlaut diacritics, without hyphens
    and spaces."""
    w = (w or "").strip().lower()
    w = (w.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
         .replace("ß", "ss"))
    w = unicodedata.normalize("NFKD", w)
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[\s\-–—/]+", "", w)


# ── Surface to check ──────────────────────────────────────────────────────
# Checking EVERY capitalised word reports, measured on two real units, 60-69 %
# of all candidates (247 and 1089 terms) — mostly everyday words such as
# "Leerzeichen", "Definition", "Recherche". Without a real dictionary "is this
# word established?" cannot be answered for the unlimited German vocabulary.
#
# The question that can be answered is: is the word TREATED like a term? That
# is observable — a coined term ends up in the glossary or is introduced
# explicitly in the text. "Leerzeichen" is never defined. On this surface the
# check list shrank on the same units from 410 to 69 and from 1583 to 71, and
# the genuine coinages ("Silbenfalle", "Scheinkonstituente",
# "Risikostufenkaskade") are in it.

_TAG = re.compile(r"<[^>]+>")
_CODE = re.compile(r"<code\b.*?</code>|<pre\b.*?</pre>|<math\b.*?</math>", re.S | re.I)
_TERM = r"[A-ZÄÖÜ][\wäöüß]+(?:[- ][A-ZÄÖÜ][\wäöüß]+){0,2}"

# Patterns with which a text ESTABLISHES a word as a term.
DEFINITION_PATTERN = [  # case-insensitive: triggers often stand at the beginning of a sentence
    re.compile(rf"\bals\s+(?:sogenannte[rsnm]?\s+)?({_TERM})\s+bezeichnet", re.I),
    re.compile(rf"\b({_TERM})\s+(?:bezeichnet|meint|beschreibt|bedeutet)\s", re.I),
    re.compile(rf"\bunter\s+(?:dem\s+Begriff\s+)?({_TERM})\s+versteht\s+man", re.I),
    re.compile(rf"\b(?:nennt|heisst|heißt)\s+man\s+({_TERM})", re.I),
    re.compile(rf"\b({_TERM})\s+(?:nennt|heisst|heißt)\s+man\b", re.I),
    re.compile(rf"\bsogenannte[rsnm]?\s+({_TERM})", re.I),
    re.compile(rf"\b(?:der|die|das)\s+Begriff\s+({_TERM})", re.I),
    re.compile(rf"\b({_TERM})\s+\(auch[:\s]", re.I),
]
# Bold markup was checked as a signal and rejected: in practice it marks the
# start of paragraphs and example words, not introductions of terms.

# Words that do not open a term (prepositions, articles, adverbs — plus the
# FUNCTION_WORDS: pronouns, demonstratives, quantity words).
OPENERS = {"fuer", "ein", "eine", "einen", "einem", "eines", "der", "die", "das",
           "dem", "den", "des", "im", "in", "am", "an", "auf", "aus", "bei", "mit",
           "from", "vom", "zur", "zum", "zu", "und", "oder", "aber", "auch", "nur",
           "praktisch", "technisch", "wichtig", "beispiel", "note", "key_point",
           "achtung", "dabei", "damit", "dadurch", "daher", "deshalb", "jedoch",
           "gleichzeitig", "anschliessend", "tatsaechlich", "innerhalb"} | FUNCTION_WORDS


def plain_text(html: str) -> str:
    t = _CODE.sub(" ", html or "")
    return _TAG.sub(" ", t)


def _sentence_starts(text: str) -> set[str]:
    """Words that are capitalised only because of their position in the sentence.

    In real data that concerned 64 and 92 candidates ("Innerhalb",
    "Gleichzeitig", "Unterscheiden") — none of them nouns.
    """
    return set(re.findall(r"(?:^|[.!?:;]\s+|<p>|<li>)\s*([A-ZÄÖÜ][\wäöüß]+)", text))


def terms_from_text(html: str) -> list[str]:
    """Terms that the text explicitly establishes as terms."""
    raw = plain_text(html)
    hits: list[str] = []
    for pattern in DEFINITION_PATTERN:
        hits += [m.group(1) for m in pattern.finditer(raw)]
    # Filter out the sentence-start effect: discard only if the term NEVER
    # occurs capitalised inside a sentence.
    starts = _sentence_starts(html or "")
    sentence_internal = set(re.findall(r"(?<=[a-zäöüß,])\s+([A-ZÄÖÜ][\wäöüß]+)", raw))
    out, seen = [], set()
    for t in hits:
        t = t.strip(" ,.;:")
        n = normal(t)
        if not t or n in seen or n in STOP:
            continue
        if normal(t.split()[0]) in OPENERS:
            continue
        header = t.split()[0]
        if header in starts and header not in sentence_internal and " " not in t:
            continue
        seen.add(n)
        out.append(t)
    return out


def check_surface(unit: dict) -> list[dict]:
    """All terms of a unit that are treated as terms.

    Returns [{"term", "source": "glossary"|"concept"|"text", "occurrence"}]
    """
    out_, seen = [], set()

    def _add(term, source, occurrence):
        n = normal(term)
        if n and n not in seen:
            seen.add(n)
            out_.append({"term": term, "source": source, "occurrence": occurrence})

    for k in unit.get("concepts") or []:
        if k.get("name"):
            _add(k["name"], "concept", k.get("id", ""))
    for g in unit.get("glossary") or []:
        if g.get("term"):
            _add(g["term"], "glossary", g.get("lesson", "glossary"))
    for l in unit.get("lessons") or []:
        html = " ".join(b.get("html", "") for b in (l.get("blocks") or [])
                        if b.get("type") in ("text", "note"))
        for b in terms_from_text(html):
            _add(b, "text", l.get("id", ""))
    return out_


def _splittable(word: str, lexicon: set[str], depth: int = 0) -> bool:
    """Greedy splitting from the left against the known vocabulary."""
    if depth > 5:
        return False
    if not word:
        return True
    if word in lexicon:
        return True
    for end in range(len(word) - MIN_TEIL, MIN_TEIL - 1, -1):
        header, rest = word[:end], word[end:]
        if header not in lexicon:
            continue
        if _splittable(rest, lexicon, depth + 1):
            return True
        for f in JOINTS:
            if rest.startswith(f) and _splittable(rest[len(f):], lexicon, depth + 1):
                return True
    return False


@dataclass
class Terminology:
    """Manages fixed terms, candidates and the replacement list."""

    fixed_terms: dict[str, dict] = field(default_factory=dict)     # normal -> {term, definition, source}
    candidates_: dict[str, dict] = field(default_factory=dict)  # normal -> {begriff, fundstelle, status, ersatz}
    blocklist: dict[str, str] = field(default_factory=dict)   # normal -> substitute term
    corpus: str = ""                                            # normalised source text
    _lexicon: set[str] = field(default_factory=lambda: set(BASE_PARTS))

    # ── Aufbau ────────────────────────────────────────────────────────────

    def set_(self, term: str, definition: str = "", source: str = "inventory") -> None:
        # The key is the CORE without the parenthetical addition — otherwise
        # "Benjamini-Hochberg-Verfahren (BH-Verfahren)" and "… (BH)" stand next
        # to each other as two terms. `covered()` already strips the bracket
        # the same way when looking up.
        core = re.sub(r"\s*\([^)]*\)\s*", " ", term or "").strip()
        n = normal(core) or normal(term)
        if not n:
            return
        entry = self.fixed_terms.setdefault(
            n, {"term": term, "definition": definition, "source": source})
        # A later source may supply a missing definition, but does not
        # overwrite an existing one.
        if definition and not entry.get("definition"):
            entry["definition"] = definition
        self._lexicon.add(n)
        self._lexicon.add(normal(term))
        for part in re.split(r"[\s\-–—/]+", term.strip()):
            if len(part) >= MIN_TEIL:
                self._lexicon.add(normal(part))

    def set_inventory(self, concepts) -> None:
        """The concept inventory is the primary authority on terminology."""
        for k in concepts or []:
            name = k.get("name") if isinstance(k, dict) else getattr(k, "name", None)
            if name:
                self.set_(name, source="inventory")

    def set_corpus(self, text: str) -> None:
        """Uploaded material: for normative texts the actual authority."""
        self.corpus = normal(text)
        for w in re.findall(r"[A-Za-zÄÖÜäöüß]{%d,}" % MIN_TEIL, text or ""):
            self._lexicon.add(normal(w))

    def load_blocklist(self, path_: Path) -> None:
        try:
            data_ = json.loads(Path(path_).read_text(encoding="utf-8"))
            # Old stocks can contain function words or meta "substitutes" —
            # those do not even get into the list.
            self.blocklist = {normal(k): v for k, v in data_.items()
                               if self._eligible_candidate(k)
                               and substitute_usable(k, v)}
        except (OSError, json.JSONDecodeError, AttributeError):
            self.blocklist = {}

    def save(self, path_: Path) -> None:
        Path(path_).parent.mkdir(parents=True, exist_ok=True)
        Path(path_).write_text(json.dumps({
            "fixed_terms": self.fixed_terms,
            "candidates": self.candidates_,
            "blocklist": self.blocklist,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── Check ──────────────────────────────────────────────────────────

    def covered(self, term: str) -> tuple[bool, str]:
        """Is the term covered by inventory, sources or composition?"""
        # Parenthetical additions are disambiguation, not part of the term:
        # "Anbieter (KI-Verordnung)" is the term "Anbieter".
        core = re.sub(r"\s*\([^)]*\)\s*", " ", term or "").strip()
        n = normal(core)
        if not n:
            return True, "empty"
        if n in self.fixed_terms:
            return True, "fixed_terms"
        if self.corpus and n in self.corpus:
            return True, "source"
        parts = [t for t in re.split(r"[\s\-–—/]+", core) if len(t) >= MIN_TEIL]
        if len(parts) > 1:
            # Multi-word terms are compositional, not new coinages, if their
            # head (last word) is covered and the determining words occur at
            # least in their stem. That catches inflection ("Freies Morphem",
            # "Expletives Subjekt") without a lemmatiser.
            header_ok = self._part_covered(parts[-1])
            rest_ok = all(self._part_covered(t, stem=True) for t in parts[:-1])
            if header_ok and rest_ok:
                return True, "mehrwort"
        if _splittable(n, self._lexicon):
            return True, "kompositum"
        return False, ""

    def _part_covered(self, word: str, stem: bool = False) -> bool:
        n = normal(word)
        if n in self.fixed_terms or n in self._lexicon:
            return True
        if self.corpus and n in self.corpus:
            return True
        if stem and len(n) >= 6 and self.corpus and n[:len(n) - 2] in self.corpus:
            return True          # inflected form: check the stem without the ending
        return False

    def check_unit(self, unit: dict) -> list[dict]:
        """Checks all terms the unit establishes as terms."""
        open_ = []
        for entry in check_surface(unit):
            hits = self._check_one(entry["term"], entry["occurrence"],
                                         entry["source"])
            if hits:
                open_.append(hits)
        return open_

    def check(self, text: str, occurrence: str = "") -> list[dict]:
        """Checks a raw text (script phase — there is no unit yet)."""
        return [t for b in terms_from_text(text)
                if (t := self._check_one(b, occurrence, "text"))]

    @staticmethod
    def _eligible_candidate(term: str) -> bool:
        """Can this hit be a term candidate at all?

        Applies MIN_LENGTH (single words) and the function word list — both
        cut off extraction artefacts ("Sie", "Hits", "Dieser Ausdruck")
        BEFORE a model has to judge them.

        Split ONLY at spaces: a hyphenated compound is ONE term.
        "Man-in-the-Middle-Angriff" or "Hier-Dokument" contain "man"/"hier"
        only as bound components — artefacts such as "Sie", "Dieser
        Ausdruck", "Tausenden von Genen" always carry their function word as a
        free word.
        """
        words = [w for w in re.split(r"\s+", (term or "").strip()) if w]
        if not words:
            return False
        if any(normal(w) in FUNCTION_WORDS for w in words):
            return False
        if len(words) == 1 and len(normal(words[0])) < MIN_LENGTH:
            return False
        return True

    def _stem_matches(self, term: str) -> dict | None:
        """Finds an already decided candidate with the same stem form.

        Besides the stem form the NUMBER OF WORDS must match: the more
        aggressive (iterative) stripping could otherwise make different terms
        collide by chance. Inflection variants change endings, never the
        number of words.
        """
        st = stem_form(term)
        if not st:
            return None
        n_words = len([w for w in re.split(r"[\s\-–—/]+", term.strip()) if w])
        for n_old, entry in self.candidates_.items():
            alt = entry.get("term") or n_old
            if len([w for w in re.split(r"[\s\-–—/]+", alt.strip()) if w]) != n_words:
                continue
            if stem_form(alt) == st:
                return entry
        return None

    def _check_one(self, term: str, occurrence: str, source: str) -> dict | None:
        if not self._eligible_candidate(term):
            return None
        n = normal(term)
        if n in self.blocklist:
            return {"term": term, "occurrence": occurrence, "source": source,
                    "reason": "blocklist", "substitute": self.blocklist[n]}
        if self.covered(term)[0]:
            return None
        if n not in self.candidates_:
            # An inflection variant of a candidate already decided? Then take
            # over the decision instead of creating a candidate that stays open
            # for good.
            alt = self._stem_matches(term)
            if alt is not None:
                if alt.get("status") == "rejected" and alt.get("substitute"):
                    self.blocklist[n] = alt["substitute"]
                    self.candidates_[n] = {"term": term, "status": "rejected",
                                          "substitute": alt["substitute"],
                                          "occurrence": occurrence}
                    return {"term": term, "occurrence": occurrence,
                            "source": source, "reason": "blocklist",
                            "substitute": alt["substitute"]}
                if alt.get("status") in ("discarded", "rejected"):
                    return None
            self.candidates_[n] = {"term": term, "occurrence": occurrence,
                                  "source": source, "status": "open", "substitute": ""}
        return {"term": term, "occurrence": occurrence, "source": source,
                "reason": "ungedeckt", "substitute": ""}

    def adopt_verdict(self, verdicts: list[dict]) -> dict[str, str]:
        """Processes the result of the model check.

        Expects entries {term, established: bool, substitute: str}.
        Established terms are fixed, non-established ones go onto the
        blocklist with a proposed substitute. Returns the replacements to
        apply.
        """
        replacements: dict[str, str] = {}
        for u in verdicts or []:
            term = (u.get("term") or "").strip()
            if not term:
                continue
            n = normal(term)
            if u.get("established"):
                self.set_(term, u.get("definition", ""), source="checked")
                self.candidates_.pop(n, None)
                continue
            # Third verdict: not a term at all (extraction artefact, everyday
            # word, sentence fragment). Discarded — NO blocklist, NO
            # replacement, NO entry in the fixed terminology.
            if u.get("no_term") or u.get("ignore"):
                self.candidates_[n] = {"term": term, "status": "discarded",
                                      "substitute": "",
                                      "occurrence": self.candidates_.get(n, {}).get("occurrence", "")}
                continue
            substitute = (u.get("substitute") or "").strip()
            # Only an insertable term may change text and terminology. Meta
            # descriptions ("Personalpronomen (kein Fachterminus)") are treated
            # like no_term — otherwise such a description ends up literally in
            # glossary definitions and script passages throughout the unit.
            if (self._eligible_candidate(term)
                    and substitute_usable(term, substitute)):
                self.blocklist[n] = substitute
                replacements[term] = substitute
                self.set_(substitute, source="substitute")
                self.candidates_[n] = {"term": term, "status": "rejected",
                                      "substitute": substitute,
                                      "occurrence": self.candidates_.get(n, {}).get("occurrence", "")}
            else:
                self.candidates_[n] = {"term": term, "status": "discarded",
                                      "substitute": "",
                                      "occurrence": self.candidates_.get(n, {}).get("occurrence", "")}
        return replacements

    # ── Application ─────────────────────────────────────────────────────────

    def replace(self, text: str, replacements: dict[str, str] | None = None) -> tuple[str, int]:
        """Applies the replacement list deterministically (at word boundaries).

        Every pair passes the same filter as in the verdict: the source must
        be eligible as a candidate (no function words, no short words), the
        target must be an insertable term. This also protects against old
        `terminology-blocklist.json` files that may still contain entries
        such as "sie" -> "Personalpronomen (kein Fachterminus)".
        """
        pairs = dict(replacements or {})
        for n, substitute in self.blocklist.items():
            entry = self.candidates_.get(n)
            if entry and entry.get("term"):
                pairs.setdefault(entry["term"], substitute)
        count = 0
        for alt, new_ in sorted(pairs.items(), key=lambda p: -len(p[0])):
            if not self._eligible_candidate(alt) or not substitute_usable(alt, new_):
                continue
            text, n = re.subn(rf"\b{re.escape(alt)}\b", new_, text)
            count += n
        return text, count

    def binding_list(self, limit: int = 40) -> str:
        """Only FIXED terms — the basis for cross_prompt."""
        rows = []
        for e in list(self.fixed_terms.values())[-limit:]:
            d = (e.get("definition") or "").strip()
            rows.append(f"{e['term']}: {d}" if d else e["term"])
        return "\n".join(rows)

    def open_candidates(self) -> list[dict]:
        return [v for v in self.candidates_.values() if v.get("status") == "open"]

    def quote(self, word_count: int) -> float:
        """Candidates per 1000 words — a figure for tracking over time."""
        return (len(self.open_candidates()) / max(word_count, 1)) * 1000
