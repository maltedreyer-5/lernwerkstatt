# -*- coding: utf-8 -*-
"""Every environment variable the code reads is documented in .env.example.

The configuration reference (docs/configuration.md) and the template are the
only places an operator learns about a setting. A variable read in the code
but missing there is a setting nobody knows about; one listed there but read
nowhere is a setting that does nothing.
"""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Read by libraries or set by the image, not by this code.
EXTERNAL = {"GRADIO_ANALYTICS_ENABLED", "PYTHONPATH", "PYTHONUNBUFFERED"}


def read_in_code() -> set[str]:
    names = set()
    files = list((REPO / "src").rglob("*.py")) + [REPO / "app.py"]
    for p in files:
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) \
                    and isinstance(n.args[0].value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]+", n.args[0].value):
                f = n.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if name in ("getenv", "get", "env_bool", "env_int", "env_float", "_env", "_bool", "_int", "_float"):
                    if name == "get" and not (isinstance(f, ast.Attribute)
                                              and ast.unparse(f.value) in ("os.environ", "environ")):
                        continue
                    names.add(n.args[0].value)
    # prefixed families: LLM1_/LLM2_ are read through a helper with a prefix
    src = (REPO / "src" / "config.py").read_text(encoding="utf-8")
    for suffix in re.findall(r'f"\{prefix\}_([A-Z_]+)"', src):
        names.update({f"LLM1_{suffix}", f"LLM2_{suffix}"})
    return names - EXTERNAL


def documented() -> set[str]:
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^#?\s?([A-Z][A-Z0-9_]+)=", text, re.M))


def test_env_documented():
    code, doc = read_in_code(), documented()
    missing, unused = sorted(code - doc), sorted(doc - code)
    assert not missing, f"read in the code but not in .env.example: {missing}"
    assert not unused, f"in .env.example but read nowhere: {unused}"
    print(f"  ok   {len(code)} variables, all documented, none unused")


if __name__ == "__main__":
    test_env_documented()
    print("ENV DOCUMENTED OK")
