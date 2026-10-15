import assert from "node:assert/strict";
import crypto from "node:crypto";
import {mkdir, writeFile} from "node:fs/promises";
import path from "node:path";
import {chromium} from "playwright";

const out = path.resolve("polo-ii-041-evidence");
await mkdir(out, {recursive:true});
const browser = await chromium.launch({channel:"chrome",headless:true,
  args:["--enable-unsafe-swiftshader","--use-gl=angle","--use-angle=swiftshader","--disable-gpu-sandbox"]});
const errors=[], consoleErrors=[];
const evidence={lane:"coimbra-041-polo-ii-vegetation-ab",successful:false,errors,consoleErrors,
 source:"unchanged accepted 032/037 GLB",browser:"system Chrome WebGL2 software GPU"};
try {
  const page = await browser.newPage({viewport:{width:1280,height:800},deviceScaleFactor:1});
  page.on("pageerror", e=>errors.push(String(e)));
  page.on("console", m=>{if(m.type()==="error")consoleErrors.push(m.text());});
  const res=await page.goto("http://127.0.0.1:4173/037/?streetQA=polo-ii&qaBackend=webgl&poloLook=after&poloTrees=before",
    {waitUntil:"domcontentloaded",timeout:120000});
  assert.equal(res?.status(),200);
  await page.waitForFunction(()=>{
    const c=globalThis.coimbra037;
    return c?.streetQA?.diagnostics().spot==="polo-ii" &&
      c?.poloVisual?.metrics().active && !c.poloVisual.metrics().pending &&
      c?.vegetation?.metrics().active===false;
  },undefined,{timeout:150000,polling:250});
  await page.waitForTimeout(1100);
  const snap = async ()=>page.evaluate(()=>{
    const g=globalThis.coimbra037;
    const cam=g.camera.getWorldPosition(g.camera.position.clone());
    const rotation=g.camera.getWorldQuaternion(g.camera.quaternion.clone());
    return {street:g.streetQA.diagnostics(),visual040:g.poloVisual.metrics(),
      vegetation041:g.vegetation.metrics(),
      cameraXYZ:cam.toArray(),cameraRotation:rotation.toArray()};
  });
  const screenshot=async name=>{
    const file="coimbra-041-"+name+".png";
    const png=await page.locator("#stage").screenshot({
      path:path.join(out,file),
      animations:"disabled",timeout:120000
    });
    assert.equal(png.subarray(0,8).toString("hex"),"89504e470d0a1a0a");
    assert.ok(png.length>20000,name+" screenshot unexpectedly small");
    return {file,bytes:png.length,
      sha256:crypto.createHash("sha256").update(png).digest("hex")};
  };

  evidence.before=await snap();
  assert.equal(evidence.before.visual040.active,true);
  assert.ok(Math.abs(evidence.before.street.measured_eye_height_m-1.7)<0.12);
  evidence.beforeScreenshot=await screenshot("baseline-040");

  await page.locator("#qa-trees").click();
  await page.waitForFunction(()=>{
    const r=globalThis.coimbra037.vegetation.metrics();
    return r.active && !r.pending && r.selectedCrowns>=15 &&
      r.hiddenSourceTriangles>200 && r.lobeInstances>r.selectedCrowns &&
      r.originalGeometryRestored;
  },undefined,{timeout:150000,polling:300});
  await page.waitForTimeout(900);
  evidence.candidate=await snap();
  assert.equal(evidence.candidate.vegetation041.originalGLBModified,false);
  assert.deepEqual(evidence.candidate.vegetation041.crop_m,[220,220]);
  assert.equal(evidence.candidate.visual040.active,true);
  assert.deepEqual(evidence.before.cameraXYZ,evidence.candidate.cameraXYZ);
  assert.deepEqual(evidence.before.cameraRotation,evidence.candidate.cameraRotation);
  evidence.candidateScreenshot=await screenshot("candidate-041");
  assert.notEqual(evidence.beforeScreenshot.sha256,evidence.candidateScreenshot.sha256);

  // A/B/A makes the visual effect independently reversible.
  await page.locator("#qa-trees").click();
  await page.waitForFunction(()=>{
    const r=globalThis.coimbra037.vegetation.metrics();
    return !r.active && !r.pending && r.originalGeometryRestored;
  },undefined,{timeout:120000,polling:300});
  await page.waitForTimeout(800);
  evidence.restored=await snap();
  assert.deepEqual(evidence.before.cameraXYZ,evidence.restored.cameraXYZ);
  assert.deepEqual(evidence.before.cameraRotation,evidence.restored.cameraRotation);
  evidence.restoredScreenshot=await screenshot("restored-040");

  await page.selectOption("#qa-location","portela");
  await page.waitForFunction(()=>{
    const g=globalThis.coimbra037;
    return g.streetQA.diagnostics().spot==="portela" &&
      !g.vegetation.metrics().active &&
      g.vegetation.metrics().originalGeometryRestored;
  },undefined,{timeout:120000,polling:350});
  evidence.outsideSpot=await snap();
  assert.equal(evidence.outsideSpot.vegetation041.spot,"portela");
  assert.equal(evidence.outsideSpot.vegetation041.active,false);

  evidence.successful=true;
  console.log(JSON.stringify({
    success:true,sourceMeshes:evidence.candidate.vegetation041.matchedSourceMeshes,
    crowns:evidence.candidate.vegetation041.selectedCrowns,
    replacedSourceTriangles:evidence.candidate.vegetation041.hiddenSourceTriangles,
    keptSourceTriangles:evidence.candidate.vegetation041.retainedSourceTriangles,
    newLobes:evidence.candidate.vegetation041.lobeInstances,
    cameraUnchanged:true,geometryRestored:true,
    screenshots:[evidence.beforeScreenshot.bytes,evidence.candidateScreenshot.bytes,evidence.restoredScreenshot.bytes],
    fpsBenchmarked:false,
  },null,2));
} catch (e) {
  evidence.failure=String(e);
  console.error("Coimbra 041 vegetation A/B failed:",e);
  console.error("Browser errors:",errors.slice(0,5),consoleErrors.slice(0,5));
  process.exitCode=1;
} finally {
  evidence.checkedAt=new Date().toISOString();
  await writeFile(path.join(out,"coimbra-041-ab.json"),JSON.stringify(evidence,null,2)+"\n");
  await browser.close();
}
