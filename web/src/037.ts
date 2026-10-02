import * as THREE from "three/webgpu";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

const app = document.getElementById("app")!;
const stage = document.getElementById("stage")!;
const status = document.getElementById("status")!;
const reference = document.getElementById("reference") as HTMLImageElement;
const toggleReference = document.getElementById("toggle-reference") as HTMLButtonElement;
const resetCamera = document.getElementById("reset-camera") as HTMLButtonElement;

function fail(error: unknown) {
  console.error(error);
  document.body.classList.add("failed");
  status.textContent = error instanceof Error ? error.message : String(error);
}

async function main() {
  const renderer = new THREE.WebGPURenderer({
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.25));
  renderer.setSize(stage.clientWidth, stage.clientHeight, false);
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = 1.05;
  app.appendChild(renderer.domElement);
  await renderer.init();

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x132033);

  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  const modelUrl = new URL("data/coimbra-032-frame181.glb", document.baseURI);
  status.textContent = "Loading accepted 032 scene…";
  const gltf = await loader.loadAsync(modelUrl.href);
  scene.add(gltf.scene);

  const importedCamera = gltf.cameras.find(
    (value): value is THREE.PerspectiveCamera => value instanceof THREE.PerspectiveCamera,
  );
  if (!importedCamera) throw new Error("Exported production camera was not found in GLB");

  const camera = importedCamera;
  camera.aspect = 1.6;
  camera.updateProjectionMatrix();

  const initialPosition = camera.position.clone();
  const initialQuaternion = camera.quaternion.clone();
  const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(initialQuaternion);
  const initialTarget = initialPosition.clone().add(forward.multiplyScalar(120));

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(initialTarget);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.update();

  let hasLight = false;
  gltf.scene.traverse((object) => {
    if ((object as THREE.Light).isLight) hasLight = true;
  });
  if (!hasLight) {
    scene.add(new THREE.HemisphereLight(0xe9f2ff, 0x625b52, 1.25));
    const sun = new THREE.DirectionalLight(0xffdab0, 2.6);
    sun.position.set(-500, 700, 900);
    scene.add(sun);
  }

  const box = new THREE.Box3().setFromObject(gltf.scene);
  const size = box.getSize(new THREE.Vector3());
  status.textContent =
    "032 source loaded · " +
    Math.round(size.x) + "×" + Math.round(size.y) + "×" + Math.round(size.z) +
    " scene units · frame 181";

  function resize() {
    const width = stage.clientWidth;
    const height = stage.clientHeight;
    renderer.setSize(width, height, false);
    camera.aspect = 1.6;
    camera.updateProjectionMatrix();
  }
  addEventListener("resize", resize);

  toggleReference.addEventListener("click", () => {
    const shown = reference.classList.toggle("shown");
    toggleReference.textContent = shown ? "Hide 032 reference" : "Show 032 reference";
  });

  resetCamera.addEventListener("click", () => {
    camera.position.copy(initialPosition);
    camera.quaternion.copy(initialQuaternion);
    controls.target.copy(initialTarget);
    controls.update();
  });

  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
  });

  Object.assign(window, {
    coimbra037: { renderer, scene, camera, controls, gltf },
  });
}

main().catch(fail);
