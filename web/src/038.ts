import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

type CameraState = {
  source_frame: number;
  fov_y_deg: number;
};

type CameraRoute = {
  version: string;
  camera_node: string;
  aspect: number;
  output_frame_count: number;
  fps: number;
  duration_seconds: number;
  animation_sample_duration_seconds: number;
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

async function main() {
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.25));
  renderer.setSize(stage.clientWidth, stage.clientHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = Math.pow(2, 0.28);
  app.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const background = new THREE.Color();
  background.setRGB(0.075, 0.095, 0.13);
  scene.background = background;

  const routeUrl = new URL("data/coimbra-032-camera-route.json", document.baseURI);
  const modelUrl = new URL("data/coimbra-032-route.glb", document.baseURI);

  status.textContent = "Loading accepted 032 route…";

  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);

  const [gltf, routeResponse] = await Promise.all([
    loader.loadAsync(modelUrl.href),
    fetch(routeUrl.href),
  ]);
  if (!routeResponse.ok) throw new Error(`Camera route HTTP ${routeResponse.status}`);

  const route = (await routeResponse.json()) as CameraRoute;
  if (
    route.output_frame_count !== 1440 ||
    route.fps !== 60 ||
    route.samples.length !== 1440
  ) {
    throw new Error("032 route contract mismatch");
  }

  scene.add(gltf.scene);
  gltf.scene.updateMatrixWorld(true);

  const candidate = gltf.scene.getObjectByName(route.camera_node);
  if (!(candidate instanceof THREE.PerspectiveCamera)) {
    throw new Error(`Baked camera ${route.camera_node} was not found in route GLB`);
  }
  const camera = candidate;
  camera.aspect = route.aspect;
  camera.updateProjectionMatrix();

  const routeClip = gltf.animations.find((clip) =>
    clip.tracks.some((track) => track.name.includes(route.camera_node)),
  ) ?? gltf.animations[0];
  if (!routeClip) throw new Error("Baked 032 camera animation was not found in route GLB");

  const mixer = new THREE.AnimationMixer(gltf.scene);
  const action = mixer.clipAction(routeClip);
  action.play();
  action.paused = true;

  const sky = new THREE.Color();
  sky.setRGB(0.58, 0.72, 1.0);
  const ground = new THREE.Color();
  ground.setRGB(0.16, 0.14, 0.12);
  scene.add(new THREE.HemisphereLight(sky, ground, 0.55));

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

    mixer.setTime(currentIndex / route.fps);
    camera.fov = sample.fov_y_deg;
    camera.aspect = route.aspect;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);

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

  playPause.addEventListener("click", () => setPlaying(!playing));

  restart.addEventListener("click", () => {
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
    const anchorIndex = Math.round((181 - 1) * (route.output_frame_count - 1) / 359);
    showCurrent(anchorIndex);
    reference.classList.add("shown");
    compare181.textContent = "Hide frame 181 reference";
    clock.textContent = "Source frame 181 · Blender reference overlay";
  });

  function resize() {
    renderer.setSize(stage.clientWidth, stage.clientHeight, false);
    camera.aspect = route.aspect;
    camera.updateProjectionMatrix();
  }
  addEventListener("resize", resize);

  showCurrent(0);
  status.textContent =
    "032 route loaded · baked Blender camera · 1440 samples · 60 fps · 24.00 s";

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
    coimbra038: { renderer, scene, camera, gltf, route, mixer, routeClip },
  });
}

main().catch(fail);
