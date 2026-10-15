import * as THREE from "three/webgpu";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { CityIndex, RoadSegment, TileData } from "./types";
import { projectToRoad, type StreetLocation } from "./street-qa-road";

// The same three inspection anchors and intended directions as Coimbra 010.
// Coordinates are local EPSG:3763 (Blender X/Y); glTF uses (X, Z, -Y).
export const STREET_QA_SPOTS = [
  { id: "sanches-brasil", label: "Sanches / Brasil", anchor: [-293.37, 851.60], toward: [-692.18, 331.73] },
  { id: "polo-ii", label: "Polo II", anchor: [-168.37, -748.07], toward: [463.44, -912.82] },
  { id: "portela", label: "Portela", anchor: [463.44, -912.82], toward: [666.22, -901.08] },
] as const;

const EYE_HEIGHT = 1.7;
const WALK_SPEED = 2.2;
const MAX_WALK_RADIUS = 45;
type Spot = (typeof STREET_QA_SPOTS)[number];

type SavedView = {
  position: THREE.Vector3;
  quaternion: THREE.Quaternion;
  target: THREE.Vector3;
  fov: number;
  near: number;
};

class GroundSampler {
  private readonly terrain: THREE.Object3D;
  private readonly top: number;
  private readonly ray = new THREE.Raycaster();

  constructor(source: THREE.Object3D) {
    source.updateMatrixWorld(true);
    const terrain = source.getObjectByName("City_Terrain");
    if (!terrain || !(terrain as THREE.Mesh).isMesh) {
      throw new Error("Exported City_Terrain mesh not found; no safe eye-height placement");
    }
    this.terrain = terrain;
    this.top = new THREE.Box3().setFromObject(source).max.y + 50;
    this.ray.far = 1000;
  }

  height(x: number, north: number): number | null {
    this.ray.set(new THREE.Vector3(x, this.top, -north), new THREE.Vector3(0, -1, 0));
    const hit = this.ray.intersectObject(this.terrain, true)[0];
    return hit ? hit.point.y : null;
  }
}

async function loadStreetRoads(spot: Spot): Promise<StreetLocation> {
  // Root 034 data are already part of the verified combined 034/037/038 Pages build.
  // Only fetch tiles near the chosen 010 anchor, not the entire Coimbra dataset.
  const indexURL = new URL("../data/coimbra/index.json", document.baseURI);
  const indexResponse = await fetch(indexURL);
  if (!indexResponse.ok) throw new Error("034 road index unavailable (HTTP " + indexResponse.status + ")");
  const index = await indexResponse.json() as CityIndex;
  if (index.schema_version !== 1 || index.tile_size <= 0) {
    throw new Error("Unexpected 034 road index schema");
  }

  const centerI = Math.floor(spot.anchor[0] / index.tile_size);
  const centerJ = Math.floor(spot.anchor[1] / index.tile_size);
  const entries = index.tiles.filter((tile) =>
    Math.abs(tile.i - centerI) <= 1 && Math.abs(tile.j - centerJ) <= 1
  );
  if (!entries.length) throw new Error("No 034 tiles near " + spot.label);
  const tileBase = new URL("./", indexURL);
  const roads: RoadSegment[] = [];
  const responses = await Promise.all(entries.map((tile) => fetch(new URL(tile.path, tileBase))));
  for (const response of responses) {
    if (!response.ok) throw new Error("Road tile unavailable (HTTP " + response.status + ")");
    const tile = await response.json() as TileData;
    roads.push(...tile.roads);
  }
  return projectToRoad(spot, roads);
}

function triggerDownload(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function quantile(sorted: number[], fraction: number) {
  if (!sorted.length) return null;
  return sorted[Math.min(sorted.length - 1, Math.ceil(fraction * sorted.length) - 1)];
}

export class StreetQA {
  private readonly select = document.getElementById("qa-location") as HTMLSelectElement;
  private readonly toggle = document.getElementById("qa-toggle") as HTMLButtonElement;
  private readonly capture = document.getElementById("qa-capture") as HTMLButtonElement;
  private readonly message = document.getElementById("qa-status")!;
  private sampler: GroundSampler | null = null;
  private readonly pressed = new Set<string>();
  private readonly times: number[] = [];
  private active = false;
  private currentSpotId: string | null = null;
  private pending = false;
  private epoch = 0;
  private lastTime = 0;
  private previousView: SavedView | null = null;
  private location: StreetLocation | null = null;
  private groundHeight: number | null = null;
  private origin: THREE.Vector3 | null = null;
  private lastGroundPoint: THREE.Vector3 | null = null;
  private pitch = 0;
  private yaw = 0;
  private dragging = false;
  private lastPointerX = 0;
  private lastPointerY = 0;

  constructor(
    private readonly renderer: THREE.WebGPURenderer,
    private readonly source: THREE.Object3D,
    private readonly camera: THREE.PerspectiveCamera,
    private readonly controls: OrbitControls,
  ) {
    this.toggle.addEventListener("click", () => {
      if (this.active) this.exit();
      else void this.enter(this.select.value);
    });
    this.select.addEventListener("change", () => {
      if (this.active) void this.enter(this.select.value);
    });
    this.capture.addEventListener("click", () => void this.saveEvidence());

    addEventListener("keydown", (event) => {
      if (!this.active || /^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test((event.target as HTMLElement).tagName)) return;
      if (["KeyW", "KeyA", "KeyS", "KeyD", "ShiftLeft", "ShiftRight"].includes(event.code)) {
        event.preventDefault();
        this.pressed.add(event.code);
      }
    });
    addEventListener("keyup", (event) => this.pressed.delete(event.code));
    addEventListener("blur", () => { this.pressed.clear(); this.dragging = false; });

    const canvas = renderer.domElement;
    canvas.addEventListener("pointerdown", (event) => {
      if (!this.active) return;
      this.dragging = true;
      this.lastPointerX = event.clientX;
      this.lastPointerY = event.clientY;
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointerup", () => { this.dragging = false; });
    canvas.addEventListener("pointercancel", () => { this.dragging = false; });
    canvas.addEventListener("pointermove", (event) => {
      if (!this.active || !this.dragging) return;
      this.yaw -= (event.clientX - this.lastPointerX) * 0.003;
      this.pitch -= (event.clientY - this.lastPointerY) * 0.003;
      this.pitch = THREE.MathUtils.clamp(this.pitch, -1.4, 1.4);
      this.lastPointerX = event.clientX;
      this.lastPointerY = event.clientY;
      this.setWorldOrientation();
    });

    const start = new URL(location.href).searchParams.get("streetQA");
    if (start && STREET_QA_SPOTS.some((spot) => spot.id === start)) {
      this.select.value = start;
      void this.enter(start);
    }
  }

  isActive() { return this.active; }

  // Read-only browser diagnostic surface for 039 screenshot CI.
  diagnostics() {
    const world = this.camera.getWorldPosition(new THREE.Vector3());
    const sorted = [...this.times].sort((a, b) => a - b);
    const mean = this.times.length
      ? this.times.reduce((sum, value) => sum + value, 0) / this.times.length
      : null;
    return {
      active: this.active,
      pending: this.pending,
      spot: this.currentSpotId,
      camera_world_xyz: world.toArray(),
      ground_y: this.groundHeight,
      measured_eye_height_m: this.groundHeight === null ? null : world.y - this.groundHeight,
      road: this.location,
      frame_sample_count: this.times.length,
      mean_frame_ms: mean,
      p95_frame_ms: quantile(sorted, 0.95),
      fps_from_mean: mean && mean > 0 ? 1000 / mean : null,
      renderer: "three.js WebGPURenderer",
      accepted_scene: "Coimbra 032 frame 181 GLB",
    };
  }

  private setWorldPosition(world: THREE.Vector3) {
    this.camera.position.copy(this.camera.parent ? this.camera.parent.worldToLocal(world.clone()) : world);
    this.camera.updateMatrixWorld(true);
  }

  private setWorldOrientation() {
    const world = new THREE.Quaternion().setFromEuler(new THREE.Euler(this.pitch, this.yaw, 0, "YXZ"));
    if (this.camera.parent) {
      const parentRotation = this.camera.parent.getWorldQuaternion(new THREE.Quaternion());
      world.premultiply(parentRotation.invert());
    }
    this.camera.quaternion.copy(world);
    this.camera.updateMatrixWorld(true);
  }

  async enter(id: string) {
    const spot = STREET_QA_SPOTS.find((item) => item.id === id);
    if (!spot || this.pending) return;
    const epoch = ++this.epoch;
    this.pending = true;
    this.toggle.disabled = true;
    this.select.disabled = true;
    this.capture.disabled = true;
    this.message.textContent = "Finding OSM road and accepted-scene ground at " + spot.label + "…";
    try {
      const location = await loadStreetRoads(spot);
      // Resolve lazily so a missing ground mesh never breaks aerial 037.
      this.sampler ??= new GroundSampler(this.source);
      const ground = this.sampler.height(location.x, location.north);
      if (ground === null) throw new Error("City_Terrain does not cover " + spot.label);
      if (epoch !== this.epoch) return;

      if (!this.active) {
        this.previousView = {
          position: this.camera.position.clone(),
          quaternion: this.camera.quaternion.clone(),
          target: this.controls.target.clone(),
          fov: this.camera.fov,
          near: this.camera.near,
        };
      }
      this.active = true;
      this.controls.enabled = false;
      this.location = location;
      this.currentSpotId = spot.id;
      this.groundHeight = ground;
      this.camera.fov = 68;
      this.camera.near = 0.12;
      this.camera.updateProjectionMatrix();

      const eye = new THREE.Vector3(location.x, ground + EYE_HEIGHT, -location.north);
      this.origin = eye.clone();
      this.lastGroundPoint = eye.clone();
      this.setWorldPosition(eye);
      this.camera.lookAt(new THREE.Vector3(
        location.x + location.forwardX * 20,
        ground + EYE_HEIGHT,
        -(location.north + location.forwardNorth * 20),
      ));
      const rotation = new THREE.Euler().setFromQuaternion(
        this.camera.getWorldQuaternion(new THREE.Quaternion()), "YXZ"
      );
      this.pitch = rotation.x;
      this.yaw = rotation.y;
      this.pressed.clear();
      this.times.length = 0;
      this.lastTime = 0;
      this.capture.disabled = false;
      this.toggle.textContent = "Return to aerial";
      this.message.textContent = spot.label + " · camera 1.7 m above City_Terrain · " +
        location.roadDistance.toFixed(1) + " m from 010 anchor · drag to look · WASD to walk";
    } catch (error) {
      // Keep an older working view selected if a different street fails to load.
      if (this.currentSpotId) this.select.value = this.currentSpotId;
      this.message.textContent = "Street QA unavailable: " + String(error);
    } finally {
      this.pending = false;
      this.toggle.disabled = false;
      this.select.disabled = false;
      this.capture.disabled = !this.active;
    }
  }

  exit() {
    this.epoch++;
    this.active = false;
    this.pressed.clear();
    this.dragging = false;
    this.capture.disabled = true;
    this.toggle.textContent = "Enter Street QA";
    this.location = null;
    this.currentSpotId = null;
    this.groundHeight = null;
    this.origin = null;
    this.lastGroundPoint = null;
    if (this.previousView) {
      this.camera.position.copy(this.previousView.position);
      this.camera.quaternion.copy(this.previousView.quaternion);
      this.camera.fov = this.previousView.fov;
      this.camera.near = this.previousView.near;
      this.camera.updateProjectionMatrix();
      this.controls.target.copy(this.previousView.target);
      this.previousView = null;
    }
    this.controls.enabled = true;
    this.controls.update();
    this.message.textContent = "Street QA off · aerial frame-181 view";
  }

  update(now: number) {
    const frameMs = this.lastTime ? Math.max(0, now - this.lastTime) : 0;
    const dt = Math.min(0.05, frameMs / 1000);
    this.lastTime = now;
    if (!this.active || dt === 0) return;
    this.times.push(frameMs);
    if (this.times.length > 240) this.times.shift();

    const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(
      this.camera.getWorldQuaternion(new THREE.Quaternion())
    );
    forward.y = 0;
    forward.normalize();
    const right = new THREE.Vector3(-forward.z, 0, forward.x);
    const move = new THREE.Vector3();
    if (this.pressed.has("KeyW")) move.add(forward);
    if (this.pressed.has("KeyS")) move.sub(forward);
    if (this.pressed.has("KeyD")) move.add(right);
    if (this.pressed.has("KeyA")) move.sub(right);
    if (move.lengthSq() === 0 || !this.origin || !this.lastGroundPoint) return;

    const speed = WALK_SPEED * (this.pressed.has("ShiftLeft") || this.pressed.has("ShiftRight") ? 2 : 1);
    move.normalize().multiplyScalar(speed * dt);
    const world = this.camera.getWorldPosition(new THREE.Vector3()).add(move);
    if (Math.hypot(world.x - this.origin.x, world.z - this.origin.z) > MAX_WALK_RADIUS) return;

    // Limit expensive terrain raycasts to roughly twice per metre of travel.
    if (Math.hypot(world.x - this.lastGroundPoint.x, world.z - this.lastGroundPoint.z) >= 0.5) {
      const ground = this.sampler!.height(world.x, -world.z);
      if (ground === null || this.groundHeight === null || Math.abs(ground - this.groundHeight) > 2) return;
      this.groundHeight = ground;
      this.lastGroundPoint.copy(world);
    }
    world.y = (this.groundHeight ?? world.y - EYE_HEIGHT) + EYE_HEIGHT;
    this.setWorldPosition(world);
  }

  private async saveEvidence() {
    if (!this.active || !this.location) return;
    this.capture.disabled = true;
    try {
      // Capture on a painted animation frame. Fail visibly if the backend
      // cannot export its canvas rather than reporting a fictional screenshot.
      const blob = await new Promise<Blob | null>((resolve) => {
        requestAnimationFrame(() => this.renderer.domElement.toBlob(resolve, "image/png"));
      });
      if (!blob || blob.size < 1024) throw new Error("Canvas PNG capture not supported by this graphics backend");
      const sorted = [...this.times].sort((a, b) => a - b);
      const avg = this.times.reduce((sum, t) => sum + t, 0) / Math.max(1, this.times.length);
      const spot = STREET_QA_SPOTS.find((item) => item.id === this.currentSpotId)!;
      const filename = "coimbra-037-street-" + spot.id + "-" + new Date().toISOString().replace(/[:.]/g, "-");
      const world = this.camera.getWorldPosition(new THREE.Vector3());
      const receipt = {
        lane: "coimbra-039-street-qa",
        source_viewer: "Coimbra 037 / accepted 032 frame-181 GLB",
        spot: spot.id,
        anchor_xy_local: [...spot.anchor],
        road_snap_distance_m: this.location.roadDistance,
        road_kind: this.location.roadKind,
        actual_eye_xyz_three: world.toArray(),
        camera_world_quaternion: this.camera.getWorldQuaternion(new THREE.Quaternion()).toArray(),
        ground_y_three: this.groundHeight,
        nominal_eye_height_m: EYE_HEIGHT,
        image: filename + ".png",
        viewport_pixels: [this.renderer.domElement.width, this.renderer.domElement.height],
        frame_sample_count: sorted.length,
        mean_frame_ms: sorted.length ? avg : null,
        p95_frame_ms: quantile(sorted, 0.95),
        fps_estimate: avg > 0 ? 1000 / avg : null,
        captured_at: new Date().toISOString(),
        limitations: ["No collision system; camera follows City_Terrain, not walkable sidewalk mesh", "Browser raster rendering is not pixel-identical to Blender Cycles"],
      };
      triggerDownload(blob, filename + ".png");
      triggerDownload(new Blob([JSON.stringify(receipt, null, 2) + "\n"], { type: "application/json" }), filename + ".json");
      this.message.textContent = "Saved PNG + JSON for " + spot.label + " · fps ≈ " +
        (receipt.fps_estimate?.toFixed(1) ?? "n/a") + " · p95 " +
        (receipt.p95_frame_ms?.toFixed(1) ?? "n/a") + " ms";
    } catch (error) {
      this.message.textContent = "Screenshot failed: " + String(error);
    } finally {
      this.capture.disabled = !this.active;
    }
  }
}
