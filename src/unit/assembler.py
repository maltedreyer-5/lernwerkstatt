# -*- coding: utf-8 -*-
"""Assembles shell + content + libraries into a single-file HTML.

Standard library only.
CLI:  python -m src.unit.assembler path/to/unit.json [output folder]
"""
from __future__ import annotations

import copy
import json

from src.unit import i18n
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.unit.terms import mark_unit

_ASSETS = Path(__file__).resolve().parents[2] / "assets"

def _vendor_list() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """File names and CDN fallback per engine from assets/vendor.json.

    scripts/copy_vendor.mjs reads the same list; a second, hand-maintained
    copy here would drift apart sooner or later. The CDN addresses pin the
    version from package.json, so that a fallback loads the same library
    as the embedded file.
    """
    manifest = json.loads((_ASSETS / "vendor.json").read_text(encoding="utf-8"))
    version = json.loads((_ASSETS.parent / "package.json").read_text(
        encoding="utf-8"))["dependencies"]
    vendor: dict[str, list[str]] = {}
    cdn: dict[str, list[str]] = {}
    for engine, entries in manifest.items():
        if engine.startswith("_"):
            continue
        vendor[engine] = [e["file"] for e in entries]
        cdn[engine] = [f"https://cdn.jsdelivr.net/npm/{e['package']}@"
                       f"{version[e['package']]}/{e['path']}" for e in entries]
    return vendor, cdn


VENDOR, CDN = _vendor_list()


@dataclass
class AssemblyResult:
    path_: Path
    kilobytes: int
    engines: list[str]
    offline: bool
    warnings_: list[str] = field(default_factory=list)
    draft: bool = False


def _esc_html(t: str) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def required_engines(unit: dict) -> set[str]:
    engines: set[str] = set()
    for l in unit.get("lessons") or []:
        for b in l.get("blocks") or []:
            _collect(b, engines)
    for m in unit.get("modules") or []:
        for b in m.get("exercises") or []:
            _collect(b, engines)
    return engines


def _collect(b: dict, engines: set[str]) -> None:
    type_ = b.get("type")
    if type_ == "chart":
        engines.add("vegalite" if b.get("engine") == "vegalite" else "chartjs")
    elif type_ == "simulator" and (b.get("output") or {}).get("kind") != "table":
        engines.add("chartjs")
    elif type_ == "diagram":
        engines.add("mermaid")


def assemble(unit: dict, output_folder: str | Path,
                vendor_folder: str | Path | None = None,
                filename: str | None = None) -> AssemblyResult:
    # Term marking for the hover explanation: deliberately here and not in
    # unit.json — the marking is presentation, not content. The unit stays the
    # editable source, repeated runs stay idempotent, and the Word export gets
    # the text unmarked.
    unit = copy.deepcopy(unit)
    marked = mark_unit(unit)
    shell = (_ASSETS / "shell.html").read_text(encoding="utf-8")
    vendor_dir = Path(vendor_folder) if vendor_folder else _ASSETS / "vendor"
    engines = required_engines(unit)

    scripts, warnings_, offline = [], [], True
    for narrow in sorted(engines):
        for i, file in enumerate(VENDOR[narrow]):
            p = vendor_dir / file
            if p.exists():
                content = p.read_text(encoding="utf-8").replace("</script", "<\\/script")
                scripts.append(f"<script>/* {file} (inline) */\n{content}\n</script>\n")
            else:
                offline = False
                scripts.append(f'<script src="{CDN[narrow][i]}"></script>\n')
                warnings_.append(
                    f"{file} not in {vendor_dir} — CDN fallback ({CDN[narrow][i]}); "
                    "the unit is therefore not offline-capable, and learners' browsers "
                    "load libraries from third-party CDNs (privacy!).")

    h = unit.get("provenance") or {}
    sources = h.get("sources") or []
    # One fallback for everything language-dependent: a unit without a
    # language would otherwise get English provenance and German controls.
    language = (unit.get("language") or "en").lower()
    T = i18n.table_(language)
    provenance = (
        T["prov_created"].format(date=datetime.now().strftime('%Y-%m-%d %H:%M')) + " · "
        + (f"{T['models']}: {h['models']} · " if h.get("models") else "")
        + (T["prov_sources"].format(sources=", ".join(sources)) if sources
           else T["prov_no_sources"])
        + (f" · {h['note']}" if h.get("note") else "")
        + " · " + T["prov_ai"]
    )

    html = (shell
            .replace("__TITLE__", _esc_html(unit.get("title") or T["learning_unit"]))
            .replace("<!--VENDOR:SCRIPTS-->", "".join(scripts))
            # Interface texts and lang attribute according to the target
            # language. Without this a Spanish learning unit would carry German
            # controls — and screen readers would speak them in the wrong
            # language.
            .replace("__LANGUAGE__", language)
            .replace("__I18N__", i18n.as_js(language))
            .replace("__UNIT_DATA__", json.dumps(unit, ensure_ascii=False).replace("</script", "<\\/script"))
            .replace("__PROVENANCE__", _esc_html(provenance)))

    output_ = Path(output_folder)
    output_.mkdir(parents=True, exist_ok=True)
    target = output_ / (filename or f"{unit.get('id') or 'learning-unit'}.html")
    target.write_text(html, encoding="utf-8")
    return AssemblyResult(
        path_=target,
        kilobytes=round(len(html.encode("utf-8")) / 1024),
        engines=sorted(engines),
        offline=offline,
        warnings_=warnings_,
    )


def assemble_file(unit_path: str | Path, output_folder: str | Path) -> AssemblyResult:
    unit = json.loads(Path(unit_path).read_text(encoding="utf-8"))
    return assemble(unit, output_folder)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Aufruf: python -m src.unit.assembler <unit.json> [ausgabeordner]")
        sys.exit(1)
    target_folder = sys.argv[2] if len(sys.argv) > 2 else str(Path(sys.argv[1]).parent.parent / "dist")
    res = assemble_file(sys.argv[1], target_folder)
    for w in res.warnings_:
        print("WARNING:", w)
    print(f"OK: {res.path_} ({res.kilobytes} KB, engines: {', '.join(res.engines) or 'none'}, "
          + ("fully offline" if res.offline else "CDN fallback active"))
