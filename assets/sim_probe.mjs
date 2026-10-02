// Runs a simulator function in isolation (called by the Python validator).
// stdin: {"code": "...", "runs": [["Default", {...}], ...]} — stdout: a JSON result.
import vm from "node:vm";

// Same fallback as the shell: accept the German field names of earlier format
// versions (serien, werte), so the probe judges what the learner will see.
function legacyFields(res) {
  if (!res || typeof res !== "object") return res;
  if (!Array.isArray(res.series) && Array.isArray(res.serien)) res.series = res.serien;
  if (Array.isArray(res.series)) for (const s of res.series)
    if (s && s.values === undefined && s.werte !== undefined) s.values = s.werte;
  return res;
}

function shortHash(t) {
  let h = 0;
  for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) | 0;
  return String(h);
}

function span(values) {
  // Without spread: `Math.min(...w)` overflows the stack for long series.
  let min = Infinity, max = -Infinity, n = 0;
  for (const w of values) {
    if (!Number.isFinite(w)) continue;
    n++; if (w < min) min = w; if (w > max) max = w;
  }
  return n ? { finite: n, min, max } : { finite: 0, min: null, max: null };
}

let raw = "";
process.stdin.on("data", d => raw += d);
process.stdin.on("end", () => {
  const { code, runs } = JSON.parse(raw);
  // The code comes from the model and is not trustworthy. node:vm is no
  // security boundary: every object from the host context that gets into the
  // context leads via `constructor.constructor` to the host `Function` and
  // with it to `process`. So only strings go in, and only one string (JSON)
  // comes out. Code generation from strings (eval, new Function) is switched
  // off in the context.
  const ctx = vm.createContext(Object.create(null),
    { codeGeneration: { strings: false, wasm: false } });
  let isFunction;
  try {
    isFunction = new vm.Script(`globalThis.__modell = (${code}); typeof globalThis.__modell === "function"`)
      .runInContext(ctx, { timeout: 200 });
  } catch (e) { console.log(JSON.stringify({ fatal: "code not evaluable: " + String(e && e.message) })); return; }
  if (isFunction !== true) { console.log(JSON.stringify({ fatal: "code is not a function" })); return; }
  const invocation = new vm.Script("JSON.stringify(globalThis.__modell(JSON.parse(globalThis.__params)))");
  const out = [];
  for (const [name, params] of runs) {
    const t0 = Date.now();
    try {
      ctx.__params = JSON.stringify(params);
      const text = invocation.runInContext(ctx, { timeout: 500 });
      const res = legacyFields(typeof text === "string" ? JSON.parse(text) : undefined);
      const form = !!(res && Array.isArray(res.x) && Array.isArray(res.series));
      // `signature` allows comparing two runs: does a slider change the output
      // at all? A control without effect is structurally free of errors and is
      // otherwise only noticed by the learner.
      // `span` reveals series that are 0 throughout — they lie invisibly on the
      // axis.
      out.push({ name, ok: true, ms: Date.now() - t0, form,
        xLen: form ? res.x.length : 0,
        signature: form ? JSON.stringify(res).length + ":" + shortHash(JSON.stringify(res)) : "",
        series: form ? res.series.map(s => {
          const values = (s && Array.isArray(s.values)) ? s.values : [];
          return { name: s && s.name, len: values.length ? values.length : -1,
                   ...span(values) };
        }) : [] });
    } catch (e) { out.push({ name, ok: false, errors: String(e && e.message) }); }
  }
  console.log(JSON.stringify({ runs: out }));
});
