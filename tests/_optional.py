"""Whether an optional package is really installed.

Some tests replace missing packages with stand-in modules in sys.modules so
that code importing them can load. Such a stand-in has no __file__, and
importlib.util.find_spec raises for it; a test needing the real package must
treat it as missing.
"""
import importlib.util
import sys


def installed(name: str) -> bool:
    module = sys.modules.get(name)
    if module is not None:
        return getattr(module, "__file__", None) is not None
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False
