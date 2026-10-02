# -*- coding: utf-8 -*-
"""Checks the interface statically, without installing Gradio.

Guards against, for instance, `ticker.tick(...).then(h_result, ...)` being
registered before `h_result` is defined. That is syntactically valid —
Python binds local names only at run time — but `build_ui()` then fails at
start-up with `UnboundLocalError`, and the container runs into a restart
loop.

This check works on the syntax tree and does not need Gradio.

Run:  python tests/test_ui_structure.py
"""
import ast
import sys
from pathlib import Path

WIZARD = Path(__file__).resolve().parents[1] / "src" / "ui" / "wizard.py"


def _build_ui(tree: ast.Module) -> ast.FunctionDef:
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "build_ui":
            return n
    raise AssertionError("build_ui() nicht gefunden")


def check(condition, name):
    print(f"  {'ok  ' if condition else 'FAIL'} {name}")
    return 0 if condition else 1


def test_names_before_use():
    """Every local name must be bound before build_ui() uses it.

    Checking only function definitions would miss `demo.load(...)`, because
    `demo` is a variable (and does not exist in this file at all; the Blocks
    context is called `ui`). So ALL local bindings are checked: functions,
    assignments, with targets, loop variables — and in addition whether a
    name is bound anywhere at all.
    """
    print("name binding in build_ui()")
    source = WIZARD.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = _build_ui(tree)

    bound: dict[str, int] = {}

    def _bind(name: str, line: int):
        if name and (name not in bound or line < bound[name]):
            bound[name] = line

    for n in ast.walk(fn):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn:
            _bind(n.name, n.lineno)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            _bind(n.id, n.lineno)
        elif isinstance(n, ast.withitem) and isinstance(n.optional_vars, ast.Name):
            _bind(n.optional_vars.id, n.optional_vars.lineno)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                _bind(a.asname or a.name.split(".")[0], n.lineno)

    # Whatever is available at module level and globally counts as present.
    outer = {t.id for m in tree.body if isinstance(m, ast.Assign)
              for t in m.targets if isinstance(t, ast.Name)}
    for m in tree.body:
        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            outer.add(m.name)
        elif isinstance(m, (ast.Import, ast.ImportFrom)):
            for a in m.names:
                outer.add(a.asname or a.name.split(".")[0])
    import builtins
    outer |= set(dir(builtins))

    too_early: set[tuple[str, int, int]] = set()
    unknown: set[tuple[str, int]] = set()

    def _check_level(nodes):
        """Only code that runs WHILE build_ui() runs.

        Names in nested handlers are only resolved when they are called — by
        then all bindings exist. Only the registration level is critical.
        """
        for kind in ast.iter_child_nodes(nodes):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(kind, ast.Name) and isinstance(kind.ctx, ast.Load):
                line = bound.get(kind.id)
                if line is None:
                    if kind.id not in outer:
                        unknown.add((kind.id, kind.lineno))
                elif kind.lineno < line:
                    too_early.add((kind.id, kind.lineno, line))
            _check_level(kind)

    _check_level(fn)

    errors = 0
    for name, used, declared in sorted(too_early):
        print(f"  FAIL {name}: used in line {used}, bound only in line {declared}")
        errors += 1
    for name, line in sorted(unknown):
        print(f"  FAIL {name}: used in line {line}, defined nowhere")
        errors += 1
    errors += check(not too_early and not unknown,
                     f"{len(bound)} local names bound correctly")
    return errors


def test_events_complete():
    """The output lists of the events must not name undefined names."""
    print("event registrations")
    source = WIZARD.read_text(encoding="utf-8")
    f = check("ticker.tick(" in source, "status ticker registered")
    f += check("al.start(" in source, "production is started as a task")
    f += check(source.count("al.start(") >= 2,
                "the continuation runs decoupled as well")
    f += check("The window can be closed" in source,
                "notice about decoupling visible")
    # h_production must not be a generator — otherwise the run hangs on the
    # request again.
    tree = ast.parse(source)
    fn = _build_ui(tree)
    prod = next((n for n in ast.walk(fn)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "h_production"), None)
    has_yield = any(isinstance(x, (ast.Yield, ast.YieldFrom))
                    for x in ast.walk(prod)) if prod else True
    f += check(prod is not None and not has_yield,
                "h_production returns instead of streaming")
    return f


def test_pipeline_methods_complete():
    """Every self.<method>(...) must exist in the class.

    Guards against a rewrite of one method whose replaced range was too large
    and took two neighbouring methods with it. The syntax check notices
    nothing — the error only shows at run time, possibly minutes after
    start-up.
    """
    print("completeness of the pipeline methods")
    import ast as _ast
    source = (WIZARD.parents[1] / "pipeline" / "learning_pipeline.py").read_text(encoding="utf-8")
    tree = _ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, _ast.ClassDef)]
    module = {n.name for n in tree.body
             if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))}
    errors = 0
    for cl in classes:
        present = {m.name for m in cl.body
                     if isinstance(m, (_ast.FunctionDef, _ast.AsyncFunctionDef))}
        present |= {t.id for m in cl.body if isinstance(m, _ast.Assign)
                      for t in m.targets if isinstance(t, _ast.Name)}
        present |= {m.target.id for m in cl.body
                      if isinstance(m, _ast.AnnAssign) and isinstance(m.target, _ast.Name)}
        called = set()
        for n in _ast.walk(cl):
            if (isinstance(n, _ast.Attribute) and isinstance(n.value, _ast.Name)
                    and n.value.id == "self"):
                called.add(n.attr)
        # Attributes set in __init__ count as present as well
        for n in _ast.walk(cl):
            if (isinstance(n, _ast.Attribute) and isinstance(n.value, _ast.Name)
                    and n.value.id == "self" and isinstance(n.ctx, _ast.Store)):
                present.add(n.attr)
        missing = sorted(called - present - module - set(dir(object)))
        for name in missing:
            print(f"  FAIL {cl.name}.{name} is called but does not exist")
            errors += 1
    return errors + check(not errors, "all self calls have a target")


if __name__ == "__main__":
    errors = (test_names_before_use() + test_events_complete()
              + test_pipeline_methods_complete())
    print(f"\n{'UI STRUCTURE OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
