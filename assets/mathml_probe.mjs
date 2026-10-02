// Converts LaTeX into MathML (called by src/unit/normalization.py).
// stdin:  {"formulas": ["Q \\cdot K^T", …], "display": false}
// stdout: {"results": [{"ok": true, "mathml": "<math…>"}, …]}
//         or {"fatal": "…"} if KaTeX is not available.
//
// KaTeX is used in MathML mode: the result is static markup without a
// run-time library and without font files. That keeps the units single-file
// and usable offline — the reason the HTML mode of KaTeX is out of the
// question here (about 20 woff2 files per unit).
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));

let katex = null;
for (const candidate of ["katex", path.join(here, "vendor", "katex.js"),
                        path.join(here, "..", "node_modules", "katex")]) {
  try { katex = require(candidate); break; } catch { /* naechster Versuch */ }
}

let raw = "";
process.stdin.on("data", d => raw += d);
process.stdin.on("end", () => {
  if (!katex) {
    console.log(JSON.stringify({ fatal: "KaTeX not installed (npm i katex)" }));
    process.exitCode = 1;
    return;
  }
  let input;
  try { input = JSON.parse(raw); }
  catch (e) {
    console.log(JSON.stringify({ fatal: "input not readable: " + e.message }));
    process.exitCode = 1;
    return;
  }

  const display = !!input.display;
  const results = (input.formulas || []).map(tex => {
    try {
      const out = katex.renderToString(String(tex), {
        output: "mathml",
        displayMode: display,
        throwOnError: true,
        strict: "ignore",
      });
      // KaTeX wraps the MathML in <span class="katex">…</span>; the unit needs
      // only the <math> element.
      const m = out.match(/<math[\s\S]*<\/math>/);
      return m ? { ok: true, mathml: m[0] }
               : { ok: false, errors: "kein MathML im KaTeX-Ergebnis" };
    } catch (e) {
      return { ok: false, errors: e.message };
    }
  });
  console.log(JSON.stringify({ results }));
});
