import assert from "node:assert/strict";
import crypto from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const base = process.env.COIMBRA_039_BASE_URL ?? "http://127.0.0.1:4173";
const outDir = path.resolve("street-qa-evidence");
const spots = ["sanches-brasil", "polo-ii", "portela"];
const seenErrors = [];
const consoleErrors = [];
const captures = [];
const MAX_RENDER_WAIT = 120_000;

await mkdir(outDir, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  // Use the GitHub runner's current Chrome rather than Playwright 1.56's
  // year-old bundled Chromium: Three.js r186 relies on modern texture swizzles.
  channel: "chrome",
  args: [
    "--enable-unsafe-swiftshader",
    "--enable-unsafe-webgpu",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--disable-gpu-sandbox",
  ],
});

try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    acceptDownloads: true,
    reducedMotion: "reduce",
  });
  console.log("Running browser version:", browser.version());
  const page = await context.newPage();
  page.on("pageerror", (err) => seenErrors.push(String(err)));
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("requestfailed", (request) => consoleErrors.push(
    request.method() + " " + request.url() + ": " + request.failure()?.errorText
  ));

  const response = await page.goto(
    base.replace(/\/$/, "") + "/037/?streetQA=sanches-brasil&qaBackend=webgl",
    { waitUntil: "domcontentloaded", timeout: MAX_RENDER_WAIT },
  );
  assert.equal(response?.status(), 200, "037 preview page must exist");

  await page.waitForFunction(() =>
    document.querySelector("#status")?.textContent?.includes("032 source loaded") &&
    !!globalThis.coimbra037?.streetQA,
    undefined,
    { polling: 300, timeout: MAX_RENDER_WAIT },
  );

  for (const spot of spots) {
    if (spot !== spots[0]) {
      await page.selectOption("#qa-location", spot);
    }
    await page.waitForFunction((expected) => {
      const qa = globalThis.coimbra037?.streetQA;
      const status = document.querySelector("#qa-status")?.textContent ?? "";
      const d = qa?.diagnostics();
      return d?.active === true &&
        d.pending === false &&
        d.spot === expected &&
        status.includes("camera 1.7 m");
    }, spot, { polling: 350, timeout: MAX_RENDER_WAIT });

    await page.waitForTimeout(1800);
    const metrics = await page.evaluate(() => globalThis.coimbra037.streetQA.diagnostics());
    assert.equal(metrics.spot, spot);
    assert.equal(metrics.active, true);
    assert.ok(metrics.qa_runtime_texture_adaptation?.resized >= 1,
      "Software-GPU Street QA should disclose its runtime orthophoto resize");
    assert.ok(metrics.road?.roadDistance >= 0 && metrics.road.roadDistance < 80,
      "An actual nearby OSM road must be used");
    assert.ok(metrics.measured_eye_height_m != null &&
      Math.abs(metrics.measured_eye_height_m - 1.7) < 0.12,
      "Actual camera must be 1.7 m above accepted City_Terrain");
    // Frame count is checked after capturing visual failure evidence.

    const pngFile = path.join(outDir, "coimbra-039-" + spot + ".png");
    const png = await page.locator("#stage").screenshot({
      path: pngFile,
      animations: "disabled",
      timeout: MAX_RENDER_WAIT,
    });
    assert.equal(png.subarray(0, 8).toString("hex"), "89504e470d0a1a0a",
      "Canvas screenshot is not PNG");
    assert.ok(png.length > 20_000, "Screenshot suspiciously small");
    captures.push({
      spot,
      pngFile: path.basename(pngFile),
      screenshot_bytes: png.length,
      screenshot_sha256: crypto.createHash("sha256").update(png).digest("hex"),
      fps_evidence: metrics.frame_sample_count >= 2
        ? "measured from requestAnimationFrame callbacks"
        : "unavailable on this headless software GPU",
      metrics,
    });
    console.log(JSON.stringify({ spot, screenshot_bytes: png.length, metrics }));
    if (metrics.frame_sample_count < 2) {
      console.warn("No reliable RAF-based FPS samples on software GPU; do not infer FPS.");
    }
  }

  const unique = new Set(captures.map((entry) => entry.screenshot_sha256));
  assert.equal(unique.size, 3, "Three independently rendered street screenshots expected");
  assert.equal(seenErrors.length, 0, "No unhandled browser errors expected");
  const report = {
    lane: "coimbra-039-street-qa",
    source_glb: "accepted Coimbra 032 / 037 publicly published GLB",
    captured_in: "GitHub-hosted Ubuntu Chromium software GPU - NOT a Mac M4 FPS benchmark",
    captures,
    page_errors: seenErrors,
    console_errors: consoleErrors,
    generated_at: new Date().toISOString(),
    reviewed_by_human: false,
  };
  await writeFile(path.join(outDir, "coimbra-039-browser-report.json"),
    JSON.stringify(report, null, 2) + "\n");
  console.log("Coimbra 039 three-location browser smoke succeeded.");
} catch (error) {
  const failure = {
    lane: "coimbra-039-street-qa",
    success: false,
    failure: String(error),
    captures,
    page_errors: seenErrors,
    console_errors: consoleErrors,
  };
  await writeFile(path.join(outDir, "coimbra-039-failure.json"),
    JSON.stringify(failure, null, 2) + "\n");
  console.error("Coimbra 039 browser smoke FAILED:", error);
  console.error("Page errors (first 5):", seenErrors.slice(0, 5));
  console.error("Console errors (first 5):", consoleErrors.slice(0, 5));
  process.exitCode = 1;
} finally {
  await browser.close();
}
