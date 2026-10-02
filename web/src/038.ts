import * as THREE from "three/webgpu";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

type CameraState = {
  source_frame: number;
  base_frame: number;
  subframe: number;
  matrix_world: number[];
  lens_mm: number;
  sensor_width_mm: number;
  fov_y_deg: number;
  output_frame?: number;
};

type CameraRoute = {
  version: string;
  resolution: [number, number];
  aspect: number;
  output_frame_count: number;
  fps: number;
  duration_seconds: number;
  sampling: string;
  anchor: CameraState;
  samples: CameraState[];
};

const app = document.getElementById("app")!;
const stage = document.getElementById("stage")!;
const status = document.getElementById("status")!;
const clock = document.getElementById("clock")!;
const timeline = document.getElementById("timeline") as HTMLInputElement;
const playPause = document.getElementById("play-pause") as HTMLButtonElement;
const restart = document.getElementById("restart") as HTMLButtonElement;
const compare181 = document.getElementById("compare-181") as HTMLButtonElement;
const reference = document.getElementById("reference") as HTMLImageElement;

function fail(error: unknown) {
  console.error(error);
  document.body.classList.add("failed");
  status.textContent = error instanceof Error ? error.message : String(error);
}

function matrixFromRows(values: number[]): THREE.Matrix4 {
  if (values.length !== 16) throw new Error("Camera route matrix must contain 16 values");
  return new THREE.Matrix4().set(
    values[0], values[1], values[2], values[3],
    values[4], values[5], values[6], values[7],
    values[8], values[9], values[10], values[11],
    values[12], values[13], values[14], values[15],
  );
}

async function main() {
  const renderer = new THREE.WebGPURenderer({
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.25));
  renderer.setSize(stage.clientWidth, stage.clientHeight, false);
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = Math.pow(2, 0.28);
  app.appendChild(renderer.domElement);
  await renderer.init();

  const scene = new THREE.Scene();
  const background = new THREE.Color();
  background.setRGB(0.075, 0.095, 0.13);
  scene.background = background;

  const routeUrl = new URL("data/coimbra-032-camera-route.json", document.baseURI);
  const modelUrl = new URL("../037/data/coimbra-032-frame181.glb", document.baseURI);

  status.textContent = "Loading accepted 032 scene and exact camera samples…";

  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);

  const [gltf, routeResponse] = await Promise.all([
    loader.loadAsync(modelUrl.href),
    fetch(routeUrl.href),
  ]);
  if (!routeResponse.ok) {
    throw new Error(`Camera route HTTP ${routeResponse.status}`);
  }
  const route = (await routeResponse.json()) as CameraRoute;

  if (route.output_frame_count !== 1440 || route.fps !== 60 || route.samples.length !== 1440) {
    throw new Error("032 route contract mismatch");
  }

  scene.add(gltf.scene);
  gltf.scene.updateMatrixWorld(true);

  const importedCamera = gltf.cameras.find(
    (value): value is THREE.PerspectiveCamera => value instanceof THREE.PerspectiveCamera,
  );
  if (!importedCamera) throw new Error("Exported frame-181 production camera was not found");

  importedCamera.updateWorldMatrix(true, false);
  const importedAnchorWorld = importedCamera.matrixWorld.clone();
  const blenderAnchorWorld = matrixFromRows(route.anchor.matrix_world);
  const alignment = importedAnchorWorld.clone().multiply(blenderAnchorWorld.clone().invert());

  scene.attach(importedCamera);
  const camera = importedCamera;
  camera.aspect = route.aspect;

  // Blender's world background and broad cool fill are not represented by glTF.
  // Keep the exported production suns and add a low-cost ambient approximation.
  const sky = new THREE.Color();
  sky.setRGB(0.58, 0.72, 1.0);
  const ground = new THREE.Color();
  ground.setRGB(0.16, 0.14, 0.12);
  scene.add(new THREE.HemisphereLight(sky, ground, 0.55));

  function applyState(sample: CameraState) {
    const blenderMatrix = matrixFromRows(sample.matrix_world);
    const webMatrix = alignment.clone().multiply(blenderMatrix);
    webMatrix.decompose(camera.position, camera.quaternion, camera.scale);
    camera.fov = sample.fov_y_deg;
    camera.aspect = route.aspect;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
  }

  let currentIndex = 0;
  let playing = true;
  let playbackStartedAt = performance.now();
  let playbackStartedIndex = 0;

  function hideReference() {
    reference.classList.remove("shown");
    compare181.textContent = "Compare frame 181";
  }

  function showCurrent(index: number) {
    currentIndex = Math.max(0, Math.min(route.samples.length - 1, index));
    const sample = route.samples[currentIndex];
    applyState(sample);
    timeline.value = String(currentIndex);
    const elapsed = currentIndex / route.fps;
    clock.textContent =
      `${elapsed.toFixed(2)} / ${route.duration_seconds.toFixed(2)} s · ` +
      `output ${currentIndex + 1}/${route.output_frame_count} · source ${sample.source_frame.toFixed(3)}`;
  }

  function setPlaying(next: boolean) {
    playing = next;
    playPause.textContent = playing ? "Pause" : "Play";
    if (playing) {
      hideReference();
      playbackStartedAt = performance.now();
      playbackStartedIndex = currentIndex;
    }
  }

  playPause.addEventListener("click", () => {
    setPlaying(!playing);
  });

  restart.addEventListener("click", () => {
    currentIndex = 0;
    showCurrent(0);
    setPlaying(true);
  });

  timeline.addEventListener("input", () => {
    setPlaying(false);
    hideReference();
    showCurrent(Number(timeline.value));
  });

  compare181.addEventListener("click", () => {
    const shown = reference.classList.contains("shown");
    if (shown) {
      hideReference();
      showCurrent(currentIndex);
      return;
    }
    setPlaying(false);
    applyState(route.anchor);
    reference.classList.add("shown");
    compare181.textContent = "Hide frame 181 reference";
    clock.textContent = "Exact source frame 181 · Blender reference overlay";
  });

  function resize() {
    renderer.setSize(stage.clientWidth, stage.clientHeight, false);
    camera.aspect = route.aspect;
    camera.updateProjectionMatrix();
  }
  addEventListener("resize", resize);

  showCurrent(0);
  status.textContent =
    "032 route loaded · 1440 native Blender samples · 60 fps · 24.00 s · AgX exposure +0.28";

  renderer.setAnimationLoop(() => {
    if (playing) {
      const elapsedFrames = Math.floor((performance.now() - playbackStartedAt) * route.fps / 1000);
      let nextIndex = playbackStartedIndex + elapsedFrames;
      if (nextIndex >= route.samples.length) {
        nextIndex %= route.samples.length;
        playbackStartedIndex = 0;
        playbackStartedAt = performance.now() - (nextIndex / route.fps) * 1000;
      }
      if (nextIndex !== currentIndex) showCurrent(nextIndex);
    }
    renderer.render(scene, camera);
  });

  Object.assign(window, {
    coimbra038: { renderer, scene, camera, gltf, route, alignment },
  });
}

main().catch(fail);
