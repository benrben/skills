#!/usr/bin/env node
/* Dependency-free JS test runner for the studio UI.
 *
 * The studio has no framework and no node_modules: testable UI logic is written
 * as pure, UMD-style modules (browser -> window, Node -> module.exports) and each
 * gets a sibling *.test.js that uses node:assert and runs with plain `node`
 * (see arch_map/ui/studio/shared/focus.test.js for the canonical example).
 *
 * This runner just discovers every *.test.js under arch_map/ui/ and runs each in
 * its own Node process, so one failing assertion can't mask the others. It exits
 * non-zero if any file fails — wired to `npm test`.
 */
"use strict";
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "arch_map", "ui");

function findTests(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules") continue;
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...findTests(p));
    else if (entry.name.endsWith(".test.js")) out.push(p);
  }
  return out;
}

const tests = findTests(ROOT).sort();
if (tests.length === 0) {
  console.error("no *.test.js files found under " + path.relative(__dirname, ROOT));
  process.exit(1);
}

let failed = 0;
for (const t of tests) {
  const rel = path.relative(__dirname, t);
  console.log("\n▶ " + rel);
  const res = spawnSync(process.execPath, [t], { stdio: "inherit" });
  if (res.status !== 0) {
    failed++;
    console.log("  ✗ FAILED: " + rel);
  }
}

console.log("\n" + (failed === 0
  ? "✓ all " + tests.length + " JS test file(s) passed"
  : "✗ " + failed + "/" + tests.length + " JS test file(s) failed"));
process.exit(failed === 0 ? 0 : 1);
