# -*- coding: utf-8 -*-
"""Actually runs `build_ui()` without an installed Gradio.

Start-up crashes such as `UnboundLocalError` or `NameError` slip through
every test that does not build the interface. The static check in
`test_ui_structure.py` catches name errors — but not wrong numbers of
arguments, forgotten components or calls on objects that do not exist like
that.

This mock reproduces just enough of Gradio for `build_ui()` to run through:
components are permissive objects, event registrations can be chained and
remember handlers with their inputs and outputs. Afterwards it checks that
every registered handler exists, is callable and matches the number of its
inputs.

Run:  python tests/test_ui_build.py
"""
import inspect
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGISTERED: list[dict] = []


class _Event:
    """Return value of an event registration — chainable via .then()."""

    def then(self, fn=None, inputs=None, outputs=None, *a, **k):
        _record("then", fn, inputs, outputs)
        return self

    def success(self, fn=None, inputs=None, outputs=None, *a, **k):
        _record("success", fn, inputs, outputs)
        return self


def _record(kind, fn, inputs, outputs):
    if fn is not None:
        REGISTERED.append({"kind": kind, "fn": fn,
                            "inputs": inputs or [], "outputs": outputs or []})


class _Component:
    """Permissive placeholder object for any Gradio component."""

    def __init__(self, *a, **k):
        self._kw = k

    # Events
    def click(self, fn=None, inputs=None, outputs=None, *a, **k):
        _record("click", fn, inputs, outputs)
        return _Event()

    def tick(self, fn=None, inputs=None, outputs=None, *a, **k):
        _record("tick", fn, inputs, outputs)
        return _Event()

    def load(self, fn=None, inputs=None, outputs=None, *a, **k):
        _record("load", fn, inputs, outputs)
        return _Event()

    def change(self, fn=None, inputs=None, outputs=None, *a, **k):
        _record("change", fn, inputs, outputs)
        return _Event()

    def upload(self, fn=None, inputs=None, outputs=None, *a, **k):
        _record("upload", fn, inputs, outputs)
        return _Event()

    def submit(self, fn=None, inputs=None, outputs=None, *a, **k):
        _record("submit", fn, inputs, outputs)
        return _Event()

    def select(self, fn=None, inputs=None, outputs=None, *a, **k):
        _record("select", fn, inputs, outputs)
        return _Event()

    # Kontextmanager (Blocks, Row, Column, Accordion, Tab, Group)
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return _Component()

    def __call__(self, *a, **k):
        return _Component()


def _add_missing_modules() -> None:
    """Mock third-party libraries that do not matter for building the UI.

    Building the interface needs neither a real OpenAI client nor httpx —
    only the imports must succeed.
    """
    for name in ("openai", "httpx", "docx", "pdfminer", "dotenv", "jsonschema"):
        if name in sys.modules:
            continue
        try:
            __import__(name)
        except ImportError:
            module = types.ModuleType(name)
            module.__getattr__ = lambda a, _n=name: _Component()  # type: ignore[attr-defined]
            module.__path__ = []  # can be treated as a package
            sys.modules[name] = module
    # Submodules fetched through from-imports
    for path_ in ("pdfminer.high_level", "docx.shared", "dotenv.main"):
        if path_ not in sys.modules:
            m = types.ModuleType(path_)
            m.__getattr__ = lambda a: _Component()  # type: ignore[attr-defined]
            sys.modules[path_] = m


def _gradio_stub() -> types.ModuleType:
    gr = types.ModuleType("gradio")

    def _factory(*a, **k):
        return _Component(*a, **k)

    for name in ("Blocks", "Row", "Column", "Accordion", "Tab", "Tabs", "Group",
                 "Markdown", "HTML", "Button", "Textbox", "Number", "Dataframe",
                 "File", "Files", "State", "Timer", "Slider", "Dropdown",
                 "Checkbox", "CheckboxGroup", "Radio", "Image", "Gallery",
                 "JSON", "Code", "Label", "Progress", "DownloadButton",
                 "UploadButton", "Plot", "Audio", "Video"):
        setattr(gr, name, _factory)
    gr.update = lambda *a, **k: {"__update__": True, **k}
    gr.themes = types.SimpleNamespace(
        Soft=_factory, Base=_factory, Default=_factory, Glass=_factory, Monochrome=_factory)
    gr.Error = type("Error", (Exception,), {})
    gr.Warning = lambda *a, **k: None
    gr.Info = lambda *a, **k: None
    return gr


def check(condition, name):
    print(f"  {'ok  ' if condition else 'FAIL'} {name}")
    return 0 if condition else 1


def test_build():
    print("build_ui() with a Gradio mock")
    _add_missing_modules()
    sys.modules["gradio"] = _gradio_stub()
    REGISTERED.clear()
    try:
        from src.ui.wizard import build_ui
        ui = build_ui()
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL build_ui() fails: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc(limit=6)
        return 1

    f = check(ui is not None, "interface built")
    f += check(len(REGISTERED) >= 10,
                f"{len(REGISTERED)} events registered")

    # Every handler must be callable and match the number of its inputs.
    for e in REGISTERED:
        fn = e["fn"]
        if not callable(fn):
            f += check(False, f"{e['kind']}: handler not callable ({fn!r})")
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        # Gradio fills parameters annotated with gr.Request itself; they are
        # not inputs of the event.
        sig = sig.replace(parameters=[p for p in sig.parameters.values()
                                      if "Request" not in str(p.annotation)])
        required = [p for p in sig.parameters.values()
                   if p.default is inspect.Parameter.empty
                   and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        optional = [p for p in sig.parameters.values()
                    if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        n_in = len(e["inputs"])
        variadic = any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values())
        if not variadic and not (len(required) <= n_in <= len(optional)):
            f += check(False,
                        f"{e['kind']} → {getattr(fn, '__name__', fn)}: {n_in} inputs, "
                        f"but {len(required)}–{len(optional)} parameters expected")
    f += check(True, "handler signatures match the inputs")

    # The essential routes must be registered. A handler that is defined but
    # never wired up would otherwise only show in operation — as a button
    # without effect.
    names = {getattr(e["fn"], "__name__", "") for e in REGISTERED}
    for required in ("h_job", "h_briefing", "h_production", "h_express",
                    "h_status", "h_result", "h_load", "h_continue",
                    "h_rework", "h_stop"):
        f += check(required in names, f"{required} is wired")
    f += _check_return_counts()
    return f


def _check_return_counts():
    """Compares the number of values each handler returns with its outputs.

    Guards against, for instance, `h_result` returning six values instead of
    five after an extension while `h_load` still unpacks five and crashes
    when a finished job is loaded. Neither the signature check nor building
    the UI finds that — the error only shows on the click.
    """
    import ast
    source = (ROOT / "src" / "ui" / "wizard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in tree.body
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "build_ui")
    handler = {n.name: n for n in ast.walk(fn)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn}

    def _counts(nodes):
        """All return sizes of a handler (return and yield)."""
        out = set()
        for k in ast.walk(nodes):
            if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)) and k is not nodes:
                continue
            value = None
            if isinstance(k, ast.Return):
                value = k.value
            elif isinstance(k, ast.Expr) and isinstance(k.value, ast.Yield):
                value = k.value.value
            if value is None:
                continue
            if isinstance(value, ast.Tuple):
                # `(a, b) + empty` cannot be counted statically
                out.add(len(value.elts))
            elif isinstance(value, ast.BinOp):
                out.add(-1)
        return out

    errors = 0
    for e in REGISTERED:
        name = getattr(e["fn"], "__name__", None)
        nodes = handler.get(name)
        n_off = len(e["outputs"])
        if nodes is None or n_off == 0:
            continue
        counts = {m for m in _counts(nodes) if m > 0}
        if counts and not all(m == n_off for m in counts):
            print(f"  FAIL {name}: returns {sorted(counts)} values, "
                  f"{n_off} outputs are registered")
            errors += 1

    # Internal calls between handlers: unpacking must match the return
    for name, nodes in handler.items():
        for k in ast.walk(nodes):
            if not (isinstance(k, ast.Assign) and isinstance(k.value, ast.Call)
                    and isinstance(k.value.func, ast.Name)
                    and k.value.func.id in handler
                    and len(k.targets) == 1
                    and isinstance(k.targets[0], ast.Tuple)):
                continue
            target = len(k.targets[0].elts)
            counts = {m for m in _counts(handler[k.value.func.id]) if m > 0}
            if counts and target not in counts:
                print(f"  FAIL {name}: unpacks {target} values from "
                      f"{k.value.func.id}(), which returns {sorted(counts)}")
                errors += 1
    return errors + check(not errors, "return sizes match the outputs")


if __name__ == "__main__":
    errors = test_build()
    print(f"\n{'UI BUILD OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
