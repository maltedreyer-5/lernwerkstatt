// Checks Mermaid source at build time (called by the Python validator).
// stdin:  {"diagrams": ["flowchart LR\n A-->B", …]}
// stdout: {"results": [{"ok": true}, {"ok": false, "errors": "…"}]}
//         or {"fatal": "…"} if the check cannot run here.
//
// IMPORTANT: Mermaid needs a DOM environment (DOMPurify) to parse. Without
// it `parse` throws "DOMPurify.addHook is not a function" — that is NOT a
// syntax error of the diagram. Mistaking one for the other would make the
// validator report every diagram as broken and block the final gate.
// Hence: provide a DOM when jsdom is there, and otherwise report every error
// that is not demonstrably a parse error as `fatal`.
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));

// Nur echte Grammatikfehler von Umgebungsproblemen unterscheiden.
const PARSE_ERROR = /parse error|lexical error|syntax error|expecting|no diagram type|unsupported/i;

let domReason = "";

async function provideDom() {
  if (typeof globalThis.document !== "undefined") return true;
  try {
    const jsdomMod = await import("jsdom");
    const JSDOM = jsdomMod.JSDOM || (jsdomMod.default && jsdomMod.default.JSDOM);
    if (!JSDOM) throw new Error("JSDOM export not found");
    const dom = new JSDOM("<!DOCTYPE html><body></body>");
    // The order is decisive: window MUST exist before dompurify or mermaid are
    // loaded — dompurify decides while the module is evaluated whether it returns
    // a factory or a ready instance.
    globalThis.window = dom.window;
    globalThis.document = dom.window.document;
    globalThis.navigator = dom.window.navigator;
    globalThis.Element = dom.window.Element;
    globalThis.Node = dom.window.Node;

    const dpMod = await import("dompurify");
    const dp = dpMod.default || dpMod;
    // Cover both cases: without window `dp` is a factory, with window already
    // the instance. Calling `dp(window)` blindly with window set would be a call
    // on an instance and throw.
    globalThis.DOMPurify = (typeof dp === "function" && typeof dp.addHook !== "function")
      ? dp(dom.window) : dp;
    if (typeof globalThis.DOMPurify.addHook !== "function") {
      throw new Error("DOMPurify without addHook — check the version");
    }
    return true;
  } catch (e) {
    // Do NOT swallow: a silent catch here would hide the cause and leave only
    // "DOMPurify.addHook is not a function"
    // uebrig gelassen.
    domReason = `DOM cannot be provided (${e && e.message ? e.message : e})`;
    return false;
  }
}

async function loadMermaid() {
  for (const k of ["mermaid",
                   path.join(here, "..", "node_modules", "mermaid"),
                   path.join(here, "vendor", "mermaid.min.js")]) {
    try {
      const m = await import(k.endsWith(".js") ? "file://" + k : k);
      return m.default || m;
    } catch { /* naechster Versuch */ }
  }
  try { return require(path.join(here, "vendor", "mermaid.min.js")); } catch { return null; }
}

let raw = "";
process.stdin.on("data", d => raw += d);
process.stdin.on("end", async () => {
  const hatDom = await provideDom();
  const mermaid = await loadMermaid();
  if (!mermaid || typeof mermaid.parse !== "function") {
    console.log(JSON.stringify({
      fatal: "Mermaid not available" + (domReason ? " — " + domReason : "") }));
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

  const results = [];
  for (const code of input.diagrams || []) {
    try {
      await mermaid.parse(String(code));
      results.push({ ok: true });
    } catch (e) {
      // Mermaid names the faulty line only FROM line 2 of the message on. Taking
      // only the first line would give "Parse error on line 2:" without the
      // content — and the error could not be found.
      const full = (e && e.message ? e.message : String(e));
      const msg = full.split("\n")[0];
      const whole = full.replace(/\s+/g, " ").slice(0, 400);
      if (!PARSE_ERROR.test(msg)) {
        // A problem of the environment, no statement about the diagram.
        // Set the exit code, so that the build-time check in the Dockerfile can
        // trigger at all.
        console.log(JSON.stringify({
          fatal: `Mermaid check cannot run (${msg})`
                 + (hatDom ? "" : " — " + (domReason || "jsdom und dompurify installieren"))
        }));
        process.exitCode = 1;
        return;
      }
      results.push({ ok: false, errors: whole });
    }
  }
  console.log(JSON.stringify({ results }));
});
