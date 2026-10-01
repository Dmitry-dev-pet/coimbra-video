import * as THREE from "three/webgpu";
import type { BuildingData, CityIndex, TileData, TileIndexEntry } from "./types";

type Detail = "far" | "near";

const terrainMaterial = new THREE.MeshStandardMaterial({
  color: 0x7f8c78,
  roughness: 0.95,
  metalness: 0,
});
const buildingMaterial = new THREE.MeshStandardMaterial({
  color: 0xc7b8a3,
  roughness: 0.82,
  metalness: 0,
});
const roadMaterials: Record<string, THREE.LineBasicMaterial> = {
  major: new THREE.LineBasicMaterial({ color: 0xf4d3a2 }),
  local: new THREE.LineBasicMaterial({ color: 0xc8c3bb }),
  service: new THREE.LineBasicMaterial({ color: 0x979795 }),
  paths: new THREE.LineBasicMaterial({ color: 0x8fa68b }),
};

function terrainMesh(data: NonNullable<TileData["terrain"]>) {
  const rows = data.ys.length;
  const cols = data.xs.length;
  const positions: number[] = [];
  const indices: number[] = [];

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      positions.push(data.xs[col], data.heights[row][col], -data.ys[row]);
    }
  }
  for (let row = 0; row < rows - 1; row++) {
    for (let col = 0; col < cols - 1; col++) {
      const a = row * cols + col;
      const b = a + 1;
      const d = (row + 1) * cols + col;
      const e = d + 1;
      indices.push(a, d, e, a, e, b);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return new THREE.Mesh(geometry, terrainMaterial);
}

function appendBuilding(
  building: BuildingData,
  positions: number[],
  indices: number[],
) {
  const polygon = building.polygon;
  if (polygon.length < 3) return;

  const start = positions.length / 3;
  for (const [x, north] of polygon) positions.push(x, building.base, -north);
  for (const [x, north] of polygon) positions.push(x, building.base + building.height, -north);

  const n = polygon.length;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    indices.push(start + i, start + j, start + n + j);
    indices.push(start + i, start + n + j, start + n + i);
  }

  const contour = polygon.map(([x, north]) => new THREE.Vector2(x, -north));
  const triangles = THREE.ShapeUtils.triangulateShape(contour, []);
  for (const triangle of triangles) {
    indices.push(
      start + n + triangle[0],
      start + n + triangle[1],
      start + n + triangle[2],
    );
  }
}

function buildingMesh(buildings: BuildingData[]) {
  const positions: number[] = [];
  const indices: number[] = [];
  for (const building of buildings) appendBuilding(building, positions, indices);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return new THREE.Mesh(geometry, buildingMaterial);
}

function roadsGroup(data: TileData) {
  const group = new THREE.Group();
  for (const kind of Object.keys(roadMaterials)) {
    const positions: number[] = [];
    for (const road of data.roads) {
      if (road.kind !== kind) continue;
      positions.push(road.a[0], road.a[2], -road.a[1]);
      positions.push(road.b[0], road.b[2], -road.b[1]);
    }
    if (!positions.length) continue;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    group.add(new THREE.LineSegments(geometry, roadMaterials[kind]));
  }
  return group;
}

function buildTile(data: TileData, detail: Detail) {
  const group = new THREE.Group();
  group.name = "CoimbraTile_" + data.i + "_" + data.j + "_" + detail;
  if (data.terrain) group.add(terrainMesh(data.terrain));
  if (data.buildings.length) group.add(buildingMesh(data.buildings));
  if (detail === "near" && data.roads.length) group.add(roadsGroup(data));

  group.updateMatrixWorld(true);
  group.traverse((object) => {
    object.matrixAutoUpdate = false;
    object.matrixWorldAutoUpdate = false;
  });
  return group;
}

function dispose(group: THREE.Group) {
  group.removeFromParent();
  group.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (mesh.geometry) mesh.geometry.dispose();
  });
}

interface LoadedTile {
  entry: TileIndexEntry;
  data: TileData;
  detail: Detail;
  group: THREE.Group;
}

export class TileStream {
  private readonly loaded = new Map<string, LoadedTile>();
  private readonly loading = new Set<string>();
  private readonly dataCache = new Map<string, TileData>();

  constructor(
    private readonly renderer: THREE.WebGPURenderer,
    private readonly scene: THREE.Scene,
    private readonly camera: THREE.PerspectiveCamera,
    private readonly index: CityIndex,
    private readonly dataBase: URL,
  ) {}

  private key(entry: TileIndexEntry) {
    return entry.i + ":" + entry.j;
  }

  private distance(entry: TileIndexEntry) {
    const x = (entry.i + 0.5) * this.index.tile_size;
    const north = (entry.j + 0.5) * this.index.tile_size;
    return Math.hypot(x - this.camera.position.x, north + this.camera.position.z);
  }

  private wanted(entry: TileIndexEntry): Detail | null {
    const distance = this.distance(entry);
    if (distance < 700) return "near";
    if (distance < 1550) return "far";
    return null;
  }

  private async loadData(entry: TileIndexEntry) {
    const key = this.key(entry);
    const cached = this.dataCache.get(key);
    if (cached) return cached;
    const response = await fetch(new URL(entry.path, this.dataBase));
    if (!response.ok) throw new Error("Tile fetch failed: " + response.status + " " + entry.path);
    const data = await response.json() as TileData;
    this.dataCache.set(key, data);
    return data;
  }

  private async ensure(entry: TileIndexEntry, detail: Detail) {
    const key = this.key(entry);
    const current = this.loaded.get(key);
    if (current?.detail === detail || this.loading.has(key)) return;
    this.loading.add(key);
    try {
      const data = await this.loadData(entry);
      const group = buildTile(data, detail);
      await this.renderer.compileAsync(group, this.camera, this.scene);
      const latest = this.loaded.get(key);
      if (latest) dispose(latest.group);
      this.scene.add(group);
      this.loaded.set(key, { entry, data, detail, group });
    } finally {
      this.loading.delete(key);
    }
  }

  async warm() {
    const entries = [...this.index.tiles]
      .sort((a, b) => this.distance(a) - this.distance(b))
      .slice(0, 12);
    await Promise.all(
      entries.map((entry) => this.ensure(entry, this.wanted(entry) ?? "far")),
    );
  }

  update() {
    for (const entry of this.index.tiles) {
      const wanted = this.wanted(entry);
      const key = this.key(entry);
      const current = this.loaded.get(key);
      if (!wanted) {
        if (current && this.distance(entry) > 1850) {
          dispose(current.group);
          this.loaded.delete(key);
        }
        continue;
      }
      if (!current || current.detail !== wanted) {
        void this.ensure(entry, wanted);
      }
    }
  }

  counts() {
    let near = 0;
    let far = 0;
    for (const tile of this.loaded.values()) {
      if (tile.detail === "near") near++;
      else far++;
    }
    return { loaded: this.loaded.size, near, far, loading: this.loading.size };
  }
}
