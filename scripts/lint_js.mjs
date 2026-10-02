// ESLint over the unit shell and the Node probes.
//
// The shell's script is assembled into every generated unit; a variable that
// shadows another, or a name used but never defined, breaks units silently.
// The rules are deliberately few: those that catch errors, not style.
//
//   npm ci            (installs eslint as a development dependency)
//   node scripts/lint_js.mjs
import { readFileSync } from "node:fs";
import { Linter } from "eslint";
import globals from "globals";

const FILES = ["assets/shell.html", "assets/sim_probe.mjs", "assets/mermaid_probe.mjs",
               "assets/mathml_probe.mjs", "assets/render_probe.mjs", "scripts/copy_vendor.mjs",
               "scripts/lint_js.mjs", "scripts/third_party_notices.mjs"];
const RULES = { "no-shadow": "error", "no-redeclare": "error", "no-undef": "error",
                "no-dupe-keys": "error", "no-shadow-restricted-names": "error",
                "no-unreachable": "error", "no-self-assign": "error" };
// Inserted by src/unit/assembler.py, or loaded as embedded libraries.
const SHELL_GLOBALS = { T: "readonly", Chart: "readonly", vegaEmbed: "readonly",
                        mermaid: "readonly" };

const linter = new Linter();
let findings = 0;
for (const file of FILES) {
  const src = readFileSync(file, "utf-8");
  const isHtml = file.endsWith(".html");
  const code = isHtml
    ? [...src.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]).join("\n")
    : src;
  const messages = linter.verify(
    // the placeholders the assembler replaces are not JavaScript yet
    code.replace(/__[A-Z0-9_]+__/g, "null"),
    [{ languageOptions: { ecmaVersion: "latest",
                          sourceType: isHtml ? "script" : "module",
                          globals: { ...(isHtml ? globals.browser : globals.node),
                                     ...(isHtml ? SHELL_GLOBALS : {}) } },
       rules: RULES }]);
  for (const m of messages) {
    findings++;
    console.log(`${file}: ${m.ruleId || "parse"}: ${m.message}`);
  }
}
console.log(findings ? `${findings} finding(s)` : "js lint: 0 findings");
process.exit(findings ? 1 : 0);
