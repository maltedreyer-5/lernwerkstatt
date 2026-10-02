// Minimal browser mock: the renderers return strings and only touch the DOM
// in the afterwards() hooks.
const stubEl = new Proxy(function(){}, {
  get: (t, p) => (p === "style" || p === "dataset" || p === "classList") ? stubEl
      : (p === "innerHTML" || p === "textContent" || p === "value") ? ""
      : (typeof p === "string" && ["length"].includes(p)) ? 0 : stubEl,
  set: () => true, apply: () => stubEl,
});
globalThis.document = new Proxy({}, { get: () => () => stubEl });
globalThis.window = new Proxy({
  addEventListener(){}, scrollTo(){}, scrollY: 0,
  matchMedia: () => ({ matches:false, addEventListener(){}, addListener(){} }),
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
}, { get: (t, p) => (p in t ? t[p] : () => {}) });
globalThis.location = { hash: "", search: "" };
globalThis.addEventListener = () => {};
globalThis.requestAnimationFrame = (f) => f();
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };

const fs = await import("node:fs");
let source = fs.readFileSync(process.argv[2] || "/tmp/probe_shell.js", "utf-8");
// pass renderers and helpers to the outside
// The script lies in an encapsulated function — the export must
// INNERHALB stehen, unmittelbar vor deren Ende.
const i = source.lastIndexOf("})();");
if (i < 0) { console.log(JSON.stringify({fatal:"end of IIFE not found"})); process.exit(1); }
source = source.slice(0, i)
  + "\nglobalThis.__renderer = typeof renderer !== 'undefined' ? renderer : null;"
  + "\nglobalThis.__UNIT = typeof UNIT !== 'undefined' ? UNIT : null;\n"
  + source.slice(i);
try {
  new Function(source)();
} catch (e) {
  console.log(JSON.stringify({ fatal: `Skript wirft beim Laden: ${e.message}` }));
  process.exit(1);
}
const R = globalThis.__renderer, UNIT = globalThis.__UNIT;
if (!R) { console.log(JSON.stringify({ fatal: "renderer not reachable" })); process.exit(1); }

const blocks = [];
for (const l of UNIT.lessons || []) for (const b of l.blocks || []) blocks.push([l.id, b]);
for (const m of UNIT.module || []) for (const b of m.exercises || []) blocks.push([m.title, b]);

const errors = [];
const html = {};
const seen = new Set();
for (const [wo, b] of blocks) {
  seen.add(b.type);
  const f = R[b.type];
  if (!f) { errors.push(`${b.type}: kein Renderer`); continue; }
  try {
    const out = f(b, { pageId: wo, blockIx: 0, quizKey: b.type === "quiz" ? wo + ":0" : null });
    if (typeof out !== "string" || !out.trim()) {
      errors.push(`${b.type}: leere Ausgabe`);
    } else if (!html[b.type]) {
      html[b.type] = out;   // one example per type for checking the content
    }
  }
  catch (e) { errors.push(`${b.type} in ${wo}: ${e.message}`); }
}
console.log(JSON.stringify({ types: [...seen].sort(), checked: blocks.length,
                             errors, html }, null, 1));
