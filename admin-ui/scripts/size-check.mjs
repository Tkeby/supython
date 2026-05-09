import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const CAP = 500 * 1024; // 500 KB
const STATIC = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "src", "supython", "admin", "static");

const html = readFileSync(join(STATIC, "index.html"), "utf-8");

// Extract entry script src
const scriptMatch = html.match(/<script[^>]+src="([^"]+)"/);
if (!scriptMatch) {
  console.error("FAIL: no entry script found in index.html");
  process.exit(1);
}

// Extract all modulepreload hrefs
const preloadMatches = [...html.matchAll(/<link[^>]+rel="modulepreload"[^>]+href="([^"]+)"/g)];

// Collect all initial-shell chunk paths (relative to static/)
const chunks = [
  "index.html",
  scriptMatch[1].replace(/^\/admin\//, ""),   // strip /admin/ prefix
  ...preloadMatches.map(m => m[1].replace(/^\/admin\//, "")),
];

let total = 0;
const sizes = [];

for (const chunk of chunks) {
  const path = join(STATIC, chunk);
  let buf;
  try {
    buf = readFileSync(path);
  } catch {
    console.error(`FAIL: initial-shell chunk not found: ${chunk}`);
    process.exit(1);
  }
  const gz = gzipSync(buf);
  total += gz.length;
  sizes.push(`${chunk}=${(gz.length / 1024).toFixed(1)}kB`);
}

const totalKB = (total / 1024).toFixed(1);
console.log(`Initial-shell chunks (${sizes.join(", ")}): total=${totalKB}kB`);

if (total > CAP) {
  console.error(`FAIL: ${totalKB}kB > ${CAP / 1024}kB cap`);
  process.exit(1);
}

console.log(`PASS: ${totalKB}kB <= ${CAP / 1024}kB cap`);
