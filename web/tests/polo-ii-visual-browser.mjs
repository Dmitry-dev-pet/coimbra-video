import assert from "node:assert/strict";
import crypto from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const dir = path.resolve("polo-ii-040-evidence");
await mkdir(dir, { recursive: true });
const pageErrors = [];
const consoleErrors = [];
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--enable-unsafe-swiftshader", "--enable-unsafe-webgpu",
    "--use-gl=angle", "--use-angle=swiftshader", "--disable-gpu-sandbox"],
});

const failure = { error: null, pageErrors, consoleErrors };
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  page.on("pageerror", error => pageErrors.push(String(error)));
  page.on("console", event => {
    if (event.type() === "error") consoleErrors.push(event.text());
  });
  const base = process.env.COIMBRA_040_BASE_URL ?? "http://127.0.0.1:4173";
  const response = await page.goto(
    base.replace(/\/$/, "") + "/037/?streetQA=polo-ii&qaBackend=webgl&poloLook=before",
    { waitUntil: "domcontentloaded", timeout: 120000 },
  );
  assert.equal(response?.status(), 200, "Expected built /037/ viewer");

  await page.waitForFunction(() => {
    const controller = globalThis.coimbra037;
    const d = controller?.streetQA?.diagnostics();
    return !!document.querySelector("#status")?.textContent?.includes("032 source loaded") &&
      d?.active && d.spot === "polo-ii" &&
      !d.pending && controller?.poloVisual?.metrics()?.mode === "baseline";
  }, undefined, { timeout: 120000, polling: 250 });

  const before = await page.evaluate(() => ({
    qa: globalThis.coimbra037.streetQA.diagnostics(),
    visual: globalThis.coimbra037.poloVisual.metrics(),
  }));
  assert.ok(Math.abs(before.qa.measured_eye_height_m - 1.7) < 0.12);
  assert.equal(before.visual.active, false);
  const beforeBuffer = await page.locator("#stage").screenshot({
    path: path.join(dir, "coimbra-040-polo-ii-before.png"),
    timeout: 120000,
  });
  assert.ok(beforeBuffer.length > 20000);

  await page.locator("#qa-polish").click();
  await page.waitForFunction(() => {
    const metrics = globalThis.coimbra037?.poloVisual?.metrics();
    return metrics && !metrics.pending && metrics.active &&
      metrics.facadeTriangles >= 10 && metrics.roadStrips >= 1 &&
      metrics.acceptedRoadTriangles > 0;
  }, undefined, { timeout: 120000, polling: 300 });

  const after = await page.evaluate(() => ({
    qa: globalThis.coimbra037.streetQA.diagnostics(),
    visual: globalThis.coimbra037.poloVisual.metrics(),
  }));
  for (let i = 0; i < 3; i++) {
    assert.ok(Math.abs(before.qa.camera_world_xyz[i] - after.qa.camera_world_xyz[i]) < 1e-5,
      "A/B camera must be exactly identical");
  }
  assert.equal(after.visual.currentSpot, "polo-ii");
  assert.deepEqual(after.visual.scope_m, [220, 220]);
  assert.equal(after.visual.originalSceneGeometryChanged, false);

  const afterBuffer = await page.locator("#stage").screenshot({
    path: path.join(dir, "coimbra-040-polo-ii-after.png"),
    timeout: 120000,
  });
  assert.ok(afterBuffer.length > 20000);
  const digest = (buf) => crypto.createHash("sha256").update(buf).digest("hex");
  assert.notEqual(digest(afterBuffer), digest(beforeBuffer), "A/B images must differ");

  // Leaving Polo II must restore baseline lighting and hide bounded overlays.
  await page.selectOption("#qa-location", "portela");
  await page.waitForFunction(() => {
    const controller = globalThis.coimbra037;
    return controller?.streetQA?.diagnostics().spot === "portela" &&
      controller?.poloVisual?.metrics().active === false;
  }, undefined, { timeout: 120000, polling: 300 });

  const report = {
    lane: "coimbra-040-polo-ii-visual-ab",
    accepted_source_scene_unchanged: true,
    after_visual_is_experimental_not_approved: true,
    captured_with: "GitHub-hosted Chrome / WebGL2 fallback / software GPU",
    no_mac_fps_claim: true,
    baseline: { screenshot: "coimbra-040-polo-ii-before.png",
      sha256: digest(beforeBuffer), bytes: beforeBuffer.length, ...before },
    candidate: { screenshot: "coimbra-040-polo-ii-after.png",
      sha256: digest(afterBuffer), bytes: afterBuffer.length, ...after },
    verify_restore_outside_polo_ii: true,
    pageErrors, consoleErrors,
    capturedAt: new Date().toISOString(),
  };
  await writeFile(path.join(dir, "coimbra-040-ab.json"), JSON.stringify(report, null, 2) + "\n");
  assert.equal(pageErrors.length, 0, "No uncaught browser errors");
  console.log(JSON.stringify({
    success: true,
    baselineBytes: beforeBuffer.length, candidateBytes: afterBuffer.length,
    facadeTriangles: after.visual.facadeTriangles,
    roadStrips: after.visual.roadStrips,
    acceptedRoadTriangles: after.visual.acceptedRoadTriangles,
    backend: before.qa.backend,
    cameraEyeM: before.qa.measured_eye_height_m,
    reportedFps: before.qa.fps_from_mean ?? null,
  }, null, 2));
} catch (e) {
  failure.error = String(e);
  console.error("Coimbra 040 visual A/B failure:", e);
  console.error("Page errors:", pageErrors.slice(0, 10));
  console.error("Console errors:", consoleErrors.slice(0, 10));
  await writeFile(path.join(dir, "coimbra-040-ab-failure.json"),
    JSON.stringify(failure, null, 2) + "\n");
  process.exitCode = 1;
} finally {
  await browser.close();
}
