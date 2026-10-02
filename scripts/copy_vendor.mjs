// Copies the renderer libraries from node_modules into assets/vendor.
//
// The list lives in assets/vendor.json, which src/unit/assembler.py reads as
// well, so the two cannot drift apart. The files come from the npm packages
// pinned in package-lock.json; npm has already checked their integrity
// hashes on install. Nothing is downloaded here.
//
// Each file gets the license text of its package prepended. The files are
// embedded into every generated unit and so passed on to learners; several
// of the minified builds carry no license notice of their own.
//
// Exit code 1 if any file is missing: a missing file makes the assembler fall
// back to a third-party CDN, which breaks the offline and privacy guarantee
// of the units. The container build treats that as an error.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const manifest = JSON.parse(readFileSync("assets/vendor.json", "utf-8"));
mkdirSync("assets/vendor", { recursive: true });
let errors = 0;
for (const [engine, entries] of Object.entries(manifest)) {
  if (engine.startsWith("_")) continue;
  for (const e of entries) {
    try {
      const pkg = JSON.parse(readFileSync(join("node_modules", e.package, "package.json"), "utf-8"));
      const code = readFileSync(join("node_modules", e.package, e.path), "utf-8");
      const license = readFileSync(join("node_modules", e.license_file), "utf-8")
        .replaceAll("*/", "* /").trim();
      const header = `/*! ${e.package} ${pkg.version} — ${pkg.license}\n${license}\n*/\n`;
      writeFileSync(join("assets/vendor", e.file), header + code);
      console.log("OK", e.file, pkg.version);
    } catch (err) {
      errors++;
      console.error("MISSING", e.file, err.message);
    }
  }
}
if (errors) {
  console.error(`\n${errors} file(s) missing — run "npm ci" first. Without them the`);
  console.error("assembler falls back to a third-party CDN and units are no longer offline.");
  process.exitCode = 1;
}
