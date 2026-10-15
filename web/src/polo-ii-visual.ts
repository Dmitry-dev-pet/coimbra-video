import * as THREE from "three/webgpu";
import type { CityIndex, RoadSegment, TileData } from "./types";

// Coimbra 040: deliberately non-authoritative visual experiment, only within
// the historical 220 × 220 m Polo II 011 photo-patch footprint.
// Accepted 032/037 scene meshes, textures, route and default viewer are untouched.
const CENTRE_X = -168.37;
const CENTRE_Z = 748.07; // Local north=-748.07 => three.js Z=+748.07
const HALF_SIZE = 110;
const MAX_FACADE_TRIANGLES = 22000;
const MAX_ROAD_SEGMENTS = 220;
const PALETTE = [0xcbb8a3, 0xc3b4a8, 0xd8c5aa, 0xb9b8aa];
const ROAD_PALETTE = [0x626967, 0x656b68, 0x596467, 0x656a6b];

function insidePatch(x: number, z: number) {
  return Math.abs(x - CENTRE_X) <= HALF_SIZE && Math.abs(z - CENTRE_Z) <= HALF_SIZE;
}

function getMeshChildren(root: THREE.Object3D): THREE.Mesh[] {
  const meshes: THREE.Mesh[] = [];
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (mesh.isMesh && mesh.geometry?.getAttribute("position")) meshes.push(mesh);
  });
  return meshes;
}

export type PoloIIMetrics = {
  active: boolean;
  requested: boolean;
  pending: boolean;
  currentSpot: string | null;
  scope_m: [number, number];
  centre_xz: [number, number];
  facadeTriangles: number;
  roadStrips: number;
  roadTriangles: number;
  originalSceneGeometryChanged: false;
  reusedAcceptedScene: true;
  cameraUnchanged: true;
  mode: string;
  warning?: string;
};

export class PoloIIVisualPass {
  private readonly toggle = document.getElementById("qa-polish") as HTMLButtonElement;
  private readonly message = document.getElementById("qa-polish-status")!;
  private readonly group = new THREE.Group();
  private requested: boolean;
  private active = false;
  private pending = false;
  private built = false;
  private generation = 0;
  private spot: string | null = null;
  private facadeTriangles = 0;
  private roadStrips = 0;
  private roadTriangles = 0;
  private warning: string | undefined;
  private original: {
    exposure: number;
    background: THREE.Color | THREE.Texture | null;
    fog: THREE.FogBase | null;
    lights: { light: THREE.Light; intensity: number }[];
  } | null = null;
  private readonly fill = new THREE.HemisphereLight(0xd7e6ef, 0x8a8277, 1.7);
  private readonly sun = new THREE.DirectionalLight(0xffe9c9, 1.3);

  constructor(
    private readonly scene: THREE.Scene,
    private readonly source: THREE.Object3D,
    private readonly renderer: THREE.WebGPURenderer,
  ) {
    this.requested = new URLSearchParams(location.search).get("poloLook") === "after";
    this.group.name = "Coimbra040_PoloII_VisualExperiment";
    this.group.visible = false;
    this.sun.position.set(-250, 600, 170);
    this.toggle.disabled = true;
    this.toggle.addEventListener("click", () => {
      this.requested = !this.requested;
      void this.refresh();
    });
    this.updateUI();
  }

  metrics(): PoloIIMetrics {
    return {
      active: this.active,
      requested: this.requested,
      pending: this.pending,
      currentSpot: this.spot,
      scope_m: [HALF_SIZE * 2, HALF_SIZE * 2],
      centre_xz: [CENTRE_X, CENTRE_Z],
      facadeTriangles: this.facadeTriangles,
      roadStrips: this.roadStrips,
      roadTriangles: this.roadTriangles,
      originalSceneGeometryChanged: false,
      reusedAcceptedScene: true,
      cameraUnchanged: true,
      mode: this.active ? "candidate" : "baseline",
      ...(this.warning ? { warning: this.warning } : {}),
    };
  }

  setSpot(id: string | null) {
    this.generation++;
    this.spot = id;
    if (id !== "polo-ii") this.disable();
    this.toggle.disabled = id !== "polo-ii";
    this.updateUI();
    if (id === "polo-ii") void this.refresh();
  }

  private updateUI() {
    this.toggle.textContent = this.active ? "Polo II: baseline" : "Polo II: visual candidate";
    if (this.pending) {
      this.message.textContent = "Building bounded Polo II comparison…";
    } else if (this.spot !== "polo-ii") {
      this.message.textContent = "Visual comparison is available only at Polo II";
    } else if (this.active) {
      this.message.textContent = "040 candidate · " + this.facadeTriangles +
        " facade triangles · " + this.roadStrips + " OSM street strips · source GLB unchanged";
    } else {
      this.message.textContent = "039 baseline · same camera, no additional 040 visuals";
    }
    if (this.warning) this.message.textContent += " · " + this.warning;
  }

  private disable() {
    if (this.active && this.original) {
      this.renderer.toneMappingExposure = this.original.exposure;
      this.scene.background = this.original.background;
      this.scene.fog = this.original.fog;
      for (const entry of this.original.lights) entry.light.intensity = entry.intensity;
      this.scene.remove(this.fill);
      this.scene.remove(this.sun);
    }
    this.group.visible = false;
    this.active = false;
    this.original = null;
    this.updateUI();
  }

  private async refresh() {
    const generation = ++this.generation;
    if (!this.requested || this.spot !== "polo-ii") {
      this.disable();
      return;
    }
    if (this.pending) return;
    this.pending = true;
    this.warning = undefined;
    this.toggle.disabled = true;
    this.updateUI();

    try {
      if (!this.built) await this.build();
      if (generation !== this.generation || this.spot !== "polo-ii" || !this.requested) return;
      if (!this.active) {
        const lights: { light: THREE.Light; intensity: number }[] = [];
        this.scene.traverse((object) => {
          const light = object as THREE.Light;
          if (light.isLight) lights.push({ light, intensity: light.intensity });
        });
        this.original = {
          exposure: this.renderer.toneMappingExposure,
          background: this.scene.background,
          fog: this.scene.fog,
          lights,
        };
        // Reduce export's harsh directional lights, add a soft ambient fill
        // and reduce blown-out white. This temporary QA look is reversible.
        for (const entry of lights) {
          entry.light.intensity = entry.intensity * 0.33;
        }
        this.scene.add(this.fill, this.sun);
        this.renderer.toneMappingExposure = 0.66;
        this.scene.background = new THREE.Color(0x9fb0bd);
        this.scene.fog = new THREE.FogExp2(0x9fb0bd, 0.00023);
        this.group.visible = true;
        this.active = true;
      }
    } catch (error) {
      this.warning = String(error);
      this.disable();
    } finally {
      this.pending = false;
      this.toggle.disabled = this.spot !== "polo-ii";
      this.updateUI();
    }
  }

  private async build() {
    this.source.updateMatrixWorld(true);
    const buildingRoot = this.source.getObjectByName("City_Buildings");
    if (!buildingRoot) throw new Error("Accepted City_Buildings mesh unavailable");

    this.buildFacades(buildingRoot);
    if (this.facadeTriangles < 10) {
      throw new Error("No accepted facades found inside 220-m Polo II patch");
    }

    const groundRoot = this.source.getObjectByName("City_Terrain");
    if (!groundRoot) throw new Error("Accepted City_Terrain unavailable");
    const roads = await this.fetchRoads();
    this.buildRoadSurface(groundRoot, roads);

    if (this.roadStrips < 1) {
      throw new Error("No accepted-terrain-grounded OSM road strips inside Polo II");
    }
    this.scene.add(this.group);
    this.built = true;
  }

  private buildFacades(buildingRoot: THREE.Object3D) {
    const buckets: number[][] = PALETTE.map(() => []);
    const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
    const edge1 = new THREE.Vector3(), edge2 = new THREE.Vector3();
    const normal = new THREE.Vector3();
    let triangles = 0;

    for (const mesh of getMeshChildren(buildingRoot)) {
      const geometry = mesh.geometry;
      const position = geometry.getAttribute("position");
      const index = geometry.getIndex();
      const count = Math.floor((index?.count ?? position.count) / 3);
      const matrix = mesh.matrixWorld;

      for (let face = 0; face < count && triangles < MAX_FACADE_TRIANGLES; face++) {
        const i0 = index ? index.getX(face * 3) : face * 3;
        const i1 = index ? index.getX(face * 3 + 1) : face * 3 + 1;
        const i2 = index ? index.getX(face * 3 + 2) : face * 3 + 2;
        a.fromBufferAttribute(position, i0).applyMatrix4(matrix);
        b.fromBufferAttribute(position, i1).applyMatrix4(matrix);
        c.fromBufferAttribute(position, i2).applyMatrix4(matrix);

        // Entirely inside the Polo II bounded footprint. No roof or ground
        // triangles: only sufficiently vertical original building surfaces.
        if (!insidePatch(a.x, a.z) || !insidePatch(b.x, b.z) || !insidePatch(c.x, c.z)) continue;
        edge1.subVectors(b, a);
        edge2.subVectors(c, a);
        normal.crossVectors(edge1, edge2);
        if (normal.lengthSq() < 0.0001) continue;
        normal.normalize();
        if (Math.abs(normal.y) > 0.32) continue;

        const cx = (a.x + b.x + c.x) / 3;
        const cz = (a.z + b.z + c.z) / 3;
        const color = Math.abs(Math.floor(cx / 24) * 29 + Math.floor(cz / 24) * 17) % PALETTE.length;
        const arr = buckets[color];
        const offset = normal.clone().multiplyScalar(0.018);
        for (const point of [a, b, c]) {
          arr.push(point.x + offset.x, point.y + offset.y, point.z + offset.z);
        }
        triangles++;
      }
      if (triangles >= MAX_FACADE_TRIANGLES) break;
    }

    for (let n = 0; n < buckets.length; n++) {
      const coords = buckets[n];
      if (!coords.length) continue;
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(coords, 3));
      geometry.computeVertexNormals();
      const material = new THREE.MeshStandardMaterial({
        color: PALETTE[n],
        roughness: 0.94,
        metalness: 0,
        side: THREE.DoubleSide,
        polygonOffset: true,
        polygonOffsetFactor: -1,
        polygonOffsetUnits: -1,
      });
      const overlay = new THREE.Mesh(geometry, material);
      overlay.frustumCulled = false;
      overlay.name = "Coimbra040_AcceptedFacade_Overlay_" + n;
      this.group.add(overlay);
    }
    this.facadeTriangles = triangles;
  }

  private async fetchRoads(): Promise<RoadSegment[]> {
    const base = new URL("../data/coimbra/index.json", document.baseURI);
    const response = await fetch(base);
    if (!response.ok) throw new Error("Published 034 OSM index unavailable");
    const index = await response.json() as CityIndex;
    if (index.schema_version !== 1 || index.tile_size !== 250) {
      throw new Error("Unexpected OSM 034 tile index");
    }

    const centreNorth = -CENTRE_Z;
    const i = Math.floor(CENTRE_X / 250);
    const j = Math.floor(centreNorth / 250);
    const entries = index.tiles.filter((tile) => Math.abs(tile.i - i) <= 1 && Math.abs(tile.j - j) <= 1);
    if (entries.length < 1 || entries.length > 9) throw new Error("Unexpected Polo II tile neighborhood");
    const json = await Promise.all(entries.map(async tile => {
      const result = await fetch(new URL(tile.path, new URL("./", base)));
      if (!result.ok) throw new Error("OSM tile HTTP " + result.status);
      return await result.json() as TileData;
    }));
    return json.flatMap((tile) => tile.roads);
  }

  private buildRoadSurface(groundRoot: THREE.Object3D, roads: RoadSegment[]) {
    const geometries: number[][] = ROAD_PALETTE.map(() => []);
    const ray = new THREE.Raycaster();
    const bounds = new THREE.Box3().setFromObject(this.source);
    ray.far = Math.max(500, bounds.max.y - bounds.min.y + 120);
    const startY = bounds.max.y + 25;
    const ground = (x: number, north: number) => {
      ray.set(new THREE.Vector3(x, startY, -north), new THREE.Vector3(0, -1, 0));
      const hit = ray.intersectObject(groundRoot, true)[0];
      return hit ? hit.point.y : null;
    };

    const unique = new Set<string>();
    let strips = 0, triangles = 0;
    for (const road of roads) {
      if (strips >= MAX_ROAD_SEGMENTS) break;
      if (road.kind === "paths") continue;
      const [ax, ay] = road.a;
      const [bx, by] = road.b;
      const dx = bx - ax, dy = by - ay;
      const length = Math.hypot(dx, dy);
      if (length < 1.0 || length > 180) continue;
      const mx = (ax + bx) / 2, mz = -(ay + by) / 2;
      if (!insidePatch(mx, mz)) continue;
      const key = [ax, ay, bx, by].map(v => v.toFixed(2)).join(":");
      if (unique.has(key)) continue;
      unique.add(key);

      const unitX = -dy / length, unitNorth = dx / length;
      const width = road.kind === "major" ? 5.2 : road.kind === "service" ? 2.8 : 4.2;
      const half = width / 2;
      const steps = Math.min(15, Math.max(1, Math.ceil(length / 8)));
      const pairs: [THREE.Vector3, THREE.Vector3][] = [];
      let valid = true;

      for (let k = 0; k <= steps; k++) {
        const t = k / steps;
        const x = ax + t * dx, north = ay + t * dy;
        const lx = x + unitX * half, ln = north + unitNorth * half;
        const rx = x - unitX * half, rn = north - unitNorth * half;
        if (!insidePatch(lx, -ln) || !insidePatch(rx, -rn)) { valid = false; break; }
        const yl = ground(lx, ln), yr = ground(rx, rn);
        if (yl === null || yr === null || Math.abs(yl - yr) > 2.5) { valid = false; break; }
        pairs.push([
          new THREE.Vector3(lx, yl + 0.055, -ln),
          new THREE.Vector3(rx, yr + 0.055, -rn),
        ]);
      }
      if (!valid || pairs.length !== steps + 1) continue;

      const kindIndex = road.kind === "major" ? 0 : road.kind === "service" ? 2 : 1;
      const bucket = geometries[kindIndex];
      const push = (p: THREE.Vector3) => bucket.push(p.x, p.y, p.z);
      for (let k = 0; k < steps; k++) {
        const [a, b] = pairs[k], [c, d] = pairs[k + 1];
        push(a); push(b); push(d);
        push(a); push(d); push(c);
        triangles += 2;
      }
      strips++;
    }

    for (let k = 0; k < geometries.length; k++) {
      const vertices = geometries[k];
      if (!vertices.length) continue;
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
      geometry.computeVertexNormals();
      const material = new THREE.MeshStandardMaterial({
        color: ROAD_PALETTE[k],
        roughness: 0.98,
        metalness: 0,
        side: THREE.DoubleSide,
        polygonOffset: true,
        polygonOffsetFactor: -2,
        polygonOffsetUnits: -2,
      });
      const overlay = new THREE.Mesh(geometry, material);
      overlay.name = "Coimbra040_OSM_RoadSurface_" + k;
      overlay.frustumCulled = false;
      this.group.add(overlay);
    }

    this.roadStrips = strips;
    this.roadTriangles = triangles;
  }
}
