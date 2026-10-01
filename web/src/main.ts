import * as THREE from "three/webgpu";
import { PerfMeter, downloadReceipt } from "./benchmark";
import { CameraController } from "./controller";
import { TileStream } from "./tiles";
import type { CityIndex } from "./types";

const app = document.getElementById("app")!;
const stats = document.getElementById("stats")!;
const exportButton = document.getElementById("export-benchmark") as HTMLButtonElement;

async function loadIndex() {
  const url = new URL("data/coimbra/index.json", document.baseURI);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(
      "Missing generated Coimbra web dataset. Run the 034 data export before serving the app.",
    );
  }
  return {
    index: await response.json() as CityIndex,
    base: new URL("./", response.url),
  };
}

async function main() {
  const renderer = new THREE.WebGPURenderer({
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.setSize(innerWidth, innerHeight);
  app.appendChild(renderer.domElement);

  const [{ index, base }] = await Promise.all([loadIndex(), renderer.init()]);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xb9c7d3);
  scene.fog = new THREE.FogExp2(0xb9c7d3, 0.00032);

  const camera = new THREE.PerspectiveCamera(48, innerWidth / innerHeight, 0.5, 7000);
  const controller = new CameraController(
    camera,
    renderer.domElement,
    index.route.anchors,
    index.route.duration_seconds,
  );

  scene.add(new THREE.HemisphereLight(0xe7f1ff, 0x6f6657, 1.8));
  const sun = new THREE.DirectionalLight(0xffe0b4, 3.1);
  sun.position.set(-720, 620, 480);
  scene.add(sun);

  const stream = new TileStream(renderer, scene, camera, index, base);
  await stream.warm();

  const meter = new PerfMeter();
  exportButton.addEventListener("click", () => {
    downloadReceipt(meter.receipt(controller.mode()));
  });

  addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });

  let previous = performance.now();
  let hudAt = 0;
  let frames = 0;

  renderer.setAnimationLoop((now) => {
    const dtMs = Math.min(100, Math.max(0.1, now - previous));
    previous = now;
    const dt = dtMs / 1000;

    controller.update(dt);
    stream.update();
    renderer.render(scene, camera);

    meter.push(dtMs);
    frames++;
    if (now - hudAt > 500) {
      hudAt = now;
      const receipt = meter.receipt(controller.mode());
      const counts = stream.counts();
      stats.textContent =
        "mode: " + controller.mode() + "\n" +
        "fps: " + receipt.fps_from_mean.toFixed(1) +
        " · p95: " + receipt.p95_frame_ms.toFixed(1) + " ms\n" +
        "tiles: " + counts.loaded + " loaded (" + counts.near + " near / " + counts.far + " far)" +
        " · " + counts.loading + " loading\n" +
        "route: " + index.route.source_contract +
        " · frames: " + frames;
    }
  });

  Object.assign(window, {
    coimbra034: {
      index,
      renderer,
      scene,
      camera,
      stream,
      benchmark: () => meter.receipt(controller.mode()),
    },
  });
}

main().catch((error) => {
  console.error(error);
  document.body.classList.add("failed");
  const target = document.getElementById("error-text")!;
  target.textContent = error instanceof Error ? error.message : String(error);
});
