#!/usr/bin/env node
/**
 * Dev-server warm-up.
 *
 * `next dev` compiles a route the first time it is requested, which on this
 * project is ~6s for `/`. Opening the browser before the dev server even
 * listens produces "localhost refused to connect"; opening it right after
 * that produces a blank tab while webpack/turbopack compiles.
 *
 * This script waits until the frontend answers, then requests every route
 * (and the static chunks they reference) so the browser opens onto an
 * already-compiled page.
 *
 * Usage: node scripts/prewarm.mjs [baseUrl] [routes...]
 */

const base = (process.argv[2] ?? "http://localhost:3000").replace(/\/$/, "");
const routes = (process.argv.slice(3).length > 0 ? process.argv.slice(3) : ["/", "/staff"]).map(
  (route) => (route.startsWith("/") ? route : `/${route}`)
);

const START = Date.now();
const READY_TIMEOUT_MS = 60_000;

const elapsed = () => `${((Date.now() - START) / 1000).toFixed(1)}s`;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function get(url) {
  const response = await fetch(url, {
    signal: AbortSignal.timeout(120_000),
    headers: { "cache-control": "no-cache" },
  });
  return response;
}

/** Wait until the page returns a successful response (compiles on first hit). */
async function waitForRoute(route) {
  const url = base + route;
  while (Date.now() - START < READY_TIMEOUT_MS) {
    try {
      const response = await get(url);
      if (response.ok) return response.text();
    } catch {
      // Not listening yet — keep waiting.
    }
    await sleep(300);
  }
  throw new Error(`no successful response from ${url}`);
}

/** Every client chunk/CSS file the HTML references, so the browser paints fast. */
function assetUrls(html) {
  const found = new Set();
  const pattern = /\/_next\/static\/[^"'\s\\]+/g;
  for (const match of html.match(pattern) ?? []) {
    if (match.includes("webpack-hmr") || match.includes("turbopack-hmr")) continue;
    found.add(base + match);
  }
  return [...found];
}

async function main() {
  const html = await waitForRoute(routes[0]);
  console.log(`    frontend ready after ${elapsed()}`);

  const assets = assetUrls(html);

  for (const route of routes.slice(1)) {
    const routeHtml = await waitForRoute(route);
    for (const asset of assetUrls(routeHtml)) assets.push(asset);
  }

  // Fetch chunks concurrently; failures are safe to ignore (the browser
  // will simply compile them itself).
  await Promise.allSettled(
    [...new Set(assets)].map((url) => get(url).then((response) => response.arrayBuffer()))
  );

  console.log(`    page compiled and warmed in ${elapsed()}`);
}

main().catch((error) => {
  console.error(`    warm-up skipped: ${error.message}`);
  process.exitCode = 0;
});
