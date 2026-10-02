# -*- coding: utf-8 -*-
"""Interface texts in several languages.

The source text of every message is its English wording, written directly
in the code:

    tr("Job #{number} was deleted.", lang, number=7)

`tr` looks the English text up in the catalog of the requested language
(`src/i18n/<lang>.py`) and fills in the parameters. A text missing from a
catalog is shown in English, never as an empty string or a raw key.

Where code reacts to a message rather than only showing it, the message
carries a stable `code` as well (see `Msg`), so that no decision depends on
the wording of a translation.

Adding a language means adding one catalog file and its code to LANGUAGES.
The texts of the generated units are a separate table (src/unit/i18n.py)
because they cover more languages than the interface.
"""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from string import Formatter

# Interface languages. English is the source language and needs no catalog.
LANGUAGES = ("en", "de")
LANGUAGE_NAMES = {"en": "English", "de": "Deutsch"}

_CATALOGS: dict[str, dict[str, str]] = {}


def default_language() -> str:
    """Interface language from APP_LANGUAGE; English if unset or unknown."""
    lang = (os.getenv("APP_LANGUAGE") or "en").strip().lower()
    return lang if lang in LANGUAGES else "en"


def catalog(lang: str) -> dict[str, str]:
    if lang == "en" or lang not in LANGUAGES:
        return {}
    if lang not in _CATALOGS:
        _CATALOGS[lang] = importlib.import_module(f"src.i18n.{lang}").CATALOG
    return _CATALOGS[lang]


def tr(text: str, lang: str | None = None, /, **params) -> str:
    """Translates an English source text and fills in its parameters.

    Positional-only, so that a template may itself use {text} or {lang}.
    """
    template = catalog(lang or default_language()).get(text, text)
    return template.format(**params) if params else template


def N_(text: str) -> str:
    """Marks a text for translation without translating it yet.

    For labels kept in tables and translated when shown; the catalog test
    finds them through this marker.
    """
    return text


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


@dataclass
class Msg:
    """A message kept in its source form until it is shown.

    `str(msg)` gives English, which is what logs and prompts to the model
    receive. `msg.render(lang)` gives the interface language. `code` is for
    code that needs to recognise a particular message.
    """
    text: str
    params: dict = field(default_factory=dict)
    code: str = ""

    def render(self, lang: str | None = None) -> str:
        return tr(self.text, lang, **{k: render(v, lang) for k, v in self.params.items()})

    def __str__(self) -> str:
        return self.render("en")


def render(value, lang: str | None = None):
    """Renders a Msg, a list of them (joined with "; ") or leaves other values.

    Lets a message carry other messages as parameters — a log line that
    lists several hints, for instance — and shows all of it in one language.
    """
    if isinstance(value, Msg):
        return value.render(lang)
    if isinstance(value, (list, tuple)) and any(isinstance(v, Msg) for v in value):
        return "; ".join(str(render(v, lang)) for v in value)
    return value
