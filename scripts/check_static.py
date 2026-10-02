"""Static check with pyflakes, used by CI and described in CONTRIBUTING.md.

Fails on every pyflakes finding except two purely stylistic classes
(unused local variables, f-strings without placeholders). The findings that
remain are the ones that break at run time: undefined names, which an import
check does not catch because they only fail when the line executes;
duplicate dictionary keys; unused or shadowed imports.
"""
import sys
from pathlib import Path

from pyflakes import api, messages, reporter

TOLERATED = (messages.UnusedVariable, messages.FStringMissingPlaceholders)
PATHS = ("src", "scripts", "tests", "app.py")


class _Filter(reporter.Reporter):
    def __init__(self):
        super().__init__(sys.stdout, sys.stderr)
        self.count = 0

    def flake(self, message):
        if isinstance(message, TOLERATED):
            return
        self.count += 1
        super().flake(message)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    rep = _Filter()
    for p in PATHS:
        api.checkRecursive([str(root / p)], rep)
    print(f"static check: {rep.count} finding(s)")
    return 1 if rep.count else 0


if __name__ == "__main__":
    sys.exit(main())
