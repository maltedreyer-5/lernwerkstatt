# -*- coding: utf-8 -*-
"""The simulator probe must not give model-generated code access to the host.

The validator executes simulator code produced by the language model in a
Node subprocess (assets/sim_probe.mjs). That code is untrusted: instructions
hidden in uploaded material can steer the model. node:vm is not a security
boundary, so the probe must never hand host-realm objects into the context.
These cases reproduce the known escape routes and check that none of them
reaches the file system, while ordinary simulator code keeps working.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.unit.validator import _ASSETS, _node_sandbox_flags, _sim_probe  # noqa: E402

RUNS = [["default", {"factor": 2}], ["other", {"factor": 3}]]


def _escape_cases(target: Path) -> dict[str, str]:
    t = str(target).replace("\\", "/")
    write = f"fs.writeFileSync('{t}', 'x')"
    return {
        "via params constructor": (
            "function modell(p){const P=p.constructor.constructor('return process')();"
            f"const fs=P.getBuiltinModule('fs'); {write};"
            "return {x:[1,2,3,4,5],series:[]};}"),
        "via Math constructor": (
            "function modell(p){const G=Math.constructor.constructor('return this')();"
            f"const fs=G.process.getBuiltinModule('fs'); {write};"
            "return {x:[1,2,3,4,5],series:[]};}"),
        "via eval": (
            "function modell(p){const fs=eval(\"process.getBuiltinModule('fs')\");"
            f"{write}; return {{x:[1,2,3,4,5],series:[]}};}}"),
    }


def _run_probe(code: str, flags: list[str]) -> dict:
    """Run the probe directly, so each protection layer can be checked alone."""
    proc = subprocess.run(
        [shutil.which("node"), *flags, str(_ASSETS / "sim_probe.mjs")],
        input=json.dumps({"code": code, "runs": RUNS}),
        capture_output=True, text=True, timeout=20)
    return json.loads(proc.stdout.strip() or "{}")


def _check_blocked(layer: str, run) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "escaped.txt"
        for name, code in _escape_cases(target).items():
            result = run(code) or {}
            assert not target.exists(), f"{name}: code wrote to the host file system"
            runs = result.get("runs") or []
            assert result.get("fatal") or not any(r.get("ok") for r in runs), \
                f"{name}: escape attempt reported as a successful run: {result}"
            print(f"  ok   {layer}: blocked {name}")


def test_context_isolation_alone():
    """Layer 1: the probe script itself, without any Node permission flags."""
    if shutil.which("node") is None:
        print("  ---  node missing, probe not checked")
        return
    _check_blocked("context isolation", lambda code: _run_probe(code, []))


def test_permission_model_alone():
    """Layer 2: the permission flags, applied to a deliberately unsafe runner."""
    node = shutil.which("node")
    if node is None:
        print("  ---  node missing, probe not checked")
        return
    flags = _node_sandbox_flags(node)
    if not flags:
        print("  ---  this Node version has no permission model; layer 1 only")
        return
    unsafe = ("import vm from 'node:vm'; let raw=''; process.stdin.on('data',d=>raw+=d);"
              "process.stdin.on('end',()=>{const {code}=JSON.parse(raw);"
              "try{const f=new vm.Script('('+code+')').runInNewContext({});"
              "f({constructor:Object});}catch(e){} console.log('{}');});")
    with tempfile.TemporaryDirectory() as tmp:
        runner = Path(tmp) / "unsafe_runner.mjs"
        runner.write_text(unsafe, encoding="utf-8")
        target = Path(tmp) / "escaped.txt"
        code = _escape_cases(target)["via params constructor"]
        read = f"--allow-fs-read={tmp}"
        subprocess.run([node, flags[0], read, str(runner)],
                       input=json.dumps({"code": code}), capture_output=True,
                       text=True, timeout=20)
        assert not target.exists(), "permission model did not stop the write"
        print(f"  ok   permission model ({flags[0]}): write refused")


def test_validator_path():
    """Both layers together, the way the validator calls the probe."""
    if shutil.which("node") is None:
        print("  ---  node missing, probe not checked")
        return
    _check_blocked("validator", lambda code: _sim_probe(code, RUNS))


def test_ordinary_simulator_still_runs():
    if shutil.which("node") is None:
        print("  ---  node missing, probe not checked")
        return
    code = ("function modell(p){const x=[0,1,2,3,4,5];"
            "return {x, series:[{name:'A', values:x.map(v=>v*p.factor)}]};}")
    result = _sim_probe(code, RUNS) or {}
    runs = result.get("runs") or []
    assert len(runs) == 2 and all(r.get("ok") and r.get("form") for r in runs), result
    assert runs[0]["signature"] != runs[1]["signature"], "parameter change had no effect"
    assert runs[0]["xLen"] == 6
    print("  ok   ordinary simulator runs and reacts to its parameter")


def test_endless_loop_is_stopped():
    if shutil.which("node") is None:
        print("  ---  node missing, probe not checked")
        return
    result = _sim_probe("function modell(p){while(true){}}", RUNS[:1]) or {}
    runs = result.get("runs") or []
    assert runs and not runs[0].get("ok"), result
    print("  ok   endless loop is stopped by the timeout")


if __name__ == "__main__":
    test_context_isolation_alone()
    test_permission_model_alone()
    test_validator_path()
    test_ordinary_simulator_still_runs()
    test_endless_loop_is_stopped()
    print("SIMULATOR SANDBOX OK")
