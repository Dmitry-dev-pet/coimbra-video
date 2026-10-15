import * as THREE from "three/webgpu";

/**
 * Coimbra 041. Reversible runtime vegetation-only visual research.
 * Source: already accepted 032/037 GLB. NO new tree locations invented.
 * GLB's BufferAttributes and original geometries are never modified/disposed.
 */
const CENTRE_X = -168.37;
const CENTRE_Z = 748.07;
const HALF_WIDTH = 110;
const INNER_MARGIN = 12;
const INNER_HALF = HALF_WIDTH - INNER_MARGIN;
const MAX_CROWNS = 1800;
const MAX_VERTICES_PER_MESH = 550000;

type VegetationSource = {
  mesh: THREE.Mesh;
  original: THREE.BufferGeometry;
  filtered: THREE.BufferGeometry;
  sourceTriangles: number;
  keptTriangles: number;
  hiddenTriangles: number;
  crowns: Crown[];
};

type Crown = {
  centre: THREE.Vector3;
  radii: THREE.Vector3;
  material: string;
  vertices: number;
};

type Component = {
  minX: number; maxX: number; minY: number; maxY: number;
  minZ: number; maxZ: number;
  count: number;
};

export type VegetationQAReceipt = {
  active: boolean;
  enabled: boolean;
  pending: boolean;
  spot: string | null;
  allowed: boolean;
  matchedSourceMeshes: number;
  selectedCrowns: number;
  hiddenSourceTriangles: number;
  retainedSourceTriangles: number;
  lobeInstances: number;
  originalGeometryRestored: boolean;
  sceneGeometrySource: string;
  crop_m: [number, number];
  margin_m: number;
  originalGLBModified: false;
  warning?: string;
};

function inCore(x: number, z: number) {
  return Math.abs(x - CENTRE_X) < INNER_HALF && Math.abs(z - CENTRE_Z) < INNER_HALF;
}

function treeMaterial(name: string): string | null {
  if (/^Semantic_Forest_Mass_[AB]$/.test(name)) return "forest";
  if (/^Semantic_Leaves_[ABC]$/.test(name)) return "leaves";
  if (/^Semantic_Scrub_[AB]$/.test(name)) return "scrub";
  if (/^Semantic_Undergrowth_(?:Green|Dry)_[AB]$/.test(name)) return "undergrowth";
  return null;
}

function getAcceptedSources(root: THREE.Object3D) {
  const sources: { mesh: THREE.Mesh; material: string }[] = [];
  root.traverse(obj => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh || !mesh.geometry?.getIndex()) return;
    const material = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
    const kind = material ? treeMaterial(material.name) : null;
    if (!kind) return;
    sources.push({ mesh, material: material.name });
  });
  return sources;
}

function analyseMesh(mesh: THREE.Mesh, material: string): VegetationSource {
  const geometry = mesh.geometry;
  const index = geometry.getIndex();
  const position = geometry.getAttribute("position");
  if (!index || !position || position.count > MAX_VERTICES_PER_MESH) {
    throw new Error("Unsupported accepted vegetation topology: " + mesh.name);
  }
  const vertexCount = position.count;
  const triangleCount = Math.floor(index.count / 3);
  const parent = new Int32Array(vertexCount);
  const sizes = new Uint8Array(vertexCount);
  for (let i = 0; i < vertexCount; i++) parent[i] = i;

  const find = (id: number): number => {
    while (parent[id] !== id) {
      parent[id] = parent[parent[id]];
      id = parent[id];
    }
    return id;
  };
  const union = (a: number, b: number) => {
    let x = find(a), y = find(b);
    if (x === y) return;
    if (sizes[x] < sizes[y]) { const t = x; x = y; y = t; }
    parent[y] = x;
    if (sizes[x] === sizes[y]) sizes[x]++;
  };
  for (let t = 0; t < triangleCount; t++) {
    const k = t * 3;
    const i = index.getX(k), j = index.getX(k + 1), l = index.getX(k + 2);
    union(i, j);
    union(i, l);
  }

  mesh.updateWorldMatrix(true, false);
  const m = mesh.matrixWorld.elements;
  const components = new Map<number, Component>();
  for (let i = 0; i < vertexCount; i++) {
    const x0 = position.getX(i), y0 = position.getY(i), z0 = position.getZ(i);
    const x = m[0] * x0 + m[4] * y0 + m[8] * z0 + m[12];
    const y = m[1] * x0 + m[5] * y0 + m[9] * z0 + m[13];
    const z = m[2] * x0 + m[6] * y0 + m[10] * z0 + m[14];
    const root = find(i);
    let c = components.get(root);
    if (!c) {
      c = { minX: x, maxX: x, minY: y, maxY: y, minZ: z, maxZ: z, count: 0 };
      components.set(root, c);
    }
    c.minX = Math.min(c.minX, x); c.maxX = Math.max(c.maxX, x);
    c.minY = Math.min(c.minY, y); c.maxY = Math.max(c.maxY, y);
    c.minZ = Math.min(c.minZ, z); c.maxZ = Math.max(c.maxZ, z);
    c.count++;
  }

  const selectedRoots = new Set<number>();
  const crowns: Crown[] = [];
  for (const [root, c] of components) {
    const width = c.maxX - c.minX;
    const depth = c.maxZ - c.minZ;
    const height = c.maxY - c.minY;
    if (width < 0.9 || depth < 0.9 || height < 0.65 ||
        width > 24 || depth > 24 || height > 25 || c.count < 9) continue;
    if (![c.minX, c.maxX].every(x => Math.abs(x - CENTRE_X) < INNER_HALF) ||
        ![c.minZ, c.maxZ].every(z => Math.abs(z - CENTRE_Z) < INNER_HALF)) continue;
    const cx = (c.minX + c.maxX) / 2;
    const cz = (c.minZ + c.maxZ) / 2;
    if (!inCore(cx, cz)) continue;
    selectedRoots.add(root);
    crowns.push({
      centre: new THREE.Vector3(cx, (c.minY + c.maxY) / 2, cz),
      radii: new THREE.Vector3(width / 2, height / 2, depth / 2),
      material,
      vertices: c.count,
    });
  }
  if (crowns.length === 0) {
    return { mesh, original: geometry, filtered: geometry,
      sourceTriangles: triangleCount, keptTriangles: triangleCount, hiddenTriangles: 0, crowns: [] };
  }

  // Create a replacement INDEX ONLY. The original mesh's source attributes,
  // normals, material, UV coordinates and geometry object stay unmodified.
  const out = vertexCount <= 65535
    ? new Uint16Array(index.count) : new Uint32Array(index.count);
  let filled = 0, hidden = 0;
  for (let t = 0; t < triangleCount; t++) {
    const k = t * 3;
    const i = index.getX(k), j = index.getX(k + 1), l = index.getX(k + 2);
    if (selectedRoots.has(find(i))) {
      hidden++;
      continue;
    }
    out[filled++] = i; out[filled++] = j; out[filled++] = l;
  }
  if (hidden <= 0) throw new Error("No accepted vegetation triangle hidden");
  const filtered = new THREE.BufferGeometry();
  for (const name of Object.keys(geometry.attributes)) {
    filtered.setAttribute(name, geometry.getAttribute(name));
  }
  filtered.setIndex(new THREE.BufferAttribute(out.slice(0, filled), 1));
  filtered.boundingBox = geometry.boundingBox?.clone() ?? null;
  filtered.boundingSphere = geometry.boundingSphere?.clone() ?? null;
  return {
    mesh, original: geometry, filtered, sourceTriangles: triangleCount,
    keptTriangles: triangleCount - hidden, hiddenTriangles: hidden, crowns,
  };
}

function palette(name: string): number {
  if (name.startsWith("Semantic_Forest")) return 0x335c3e;
  if (name.startsWith("Semantic_Scrub")) return 0x4a6b41;
  if (name.includes("Undergrowth_Dry")) return 0x686d41;
  if (name.includes("Undergrowth")) return 0x47653b;
  return 0x3c6745;
}

function createLobes(source: VegetationSource): THREE.InstancedMesh | null {
  if (source.crowns.length === 0) return null;
  const tint = palette(source.crowns[0].material);
  // This is an illustrative, intentionally UNLIT vegetation colour swatch:
  // the accepted 032/040 lights blow physically lit greens almost white in
  // this diagnostic renderer. Keep tone mapping off for the foliage layer
  // rather than altering any accepted source or global scene lighting.
  const material = new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false });
  const geometry = new THREE.SphereGeometry(1, 11, 8);
  const mesh = new THREE.InstancedMesh(geometry, material, source.crowns.length * 5);
  mesh.name = "Coimbra041_FoliageClusters_" + source.mesh.name;
  mesh.frustumCulled = false;
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  const transform = new THREE.Object3D();
  let instance = 0;
  for (const crown of source.crowns) {
    const radii = crown.radii;
    const seed = Math.sin(crown.centre.x * 12.9898 + crown.centre.z * 78.233) * 43758.5453;
    const phase = seed - Math.floor(seed);
    const angle = phase * Math.PI * 2;
    const ca = Math.cos(angle), sa = Math.sin(angle);
    // Five small overlapping crowns give scalloped foliage rather than one
    // giant white ellipsoid. All shapes derive from the accepted crown bbox.
    const variants: [number, number, number, number, number, number, number][] = [
      [-0.30, -0.18,  0.03, 0.73, 0.78, 0.74, 0.83],
      [ 0.27, -0.12,  0.17, 0.70, 0.67, 0.72, 1.00],
      [-0.04,  0.30, -0.10, 0.75, 0.66, 0.73, 0.92],
      [-0.27,  0.26,  0.26, 0.56, 0.56, 0.60, 1.08],
      [ 0.30,  0.22,  0.29, 0.54, 0.59, 0.56, 0.90],
    ];
    for (const [ox, oz, oy, sx, sy, sz, shade] of variants) {
      const dx = ox * ca - oz * sa;
      const dz = ox * sa + oz * ca;
      transform.position.set(crown.centre.x + dx * radii.x,
        crown.centre.y + oy * radii.y, crown.centre.z + dz * radii.z);
      transform.scale.set(radii.x * sx, radii.y * sy, radii.z * sz);
      transform.rotation.set(0, 0, 0);
      transform.updateMatrix();
      mesh.setMatrixAt(instance, transform.matrix);
      const color = new THREE.Color(tint).multiplyScalar(shade * (0.96 + phase * 0.08));
      mesh.setColorAt(instance, color);
      instance++;
    }
  }
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  mesh.count = instance;
  return mesh;
}

export class PoloIIVegetationPass {
  private readonly button = document.getElementById("qa-trees") as HTMLButtonElement;
  private readonly status = document.getElementById("qa-trees-status")!;
  private readonly group = new THREE.Group();
  private readonly enabledFromURL = new URLSearchParams(location.search).get("poloTrees") === "after";
  private requested = this.enabledFromURL;
  private active = false;
  private loading = false;
  private built = false;
  private spot: string | null = null;
  private lastAllowed = false;
  private warning: string | undefined;
  private sources: VegetationSource[] = [];
  private lobeInstances = 0;

  constructor(private readonly scene: THREE.Scene,
    private readonly source: THREE.Object3D,
    private readonly is040Active: () => boolean) {
    this.group.name = "Coimbra041_PoloII_OnlyVegetation";
    this.group.visible = false;
    this.button.addEventListener("click", () => {
      this.requested = !this.requested;
      void this.refresh();
    });
    this.updateUI();
  }

  setSpot(spot: string | null) {
    this.spot = spot;
    if (spot !== "polo-ii") this.disable();
    this.updateUI();
    if (spot === "polo-ii") void this.refresh();
  }

  update() {
    const allowed = this.spot === "polo-ii" && this.is040Active();
    if (allowed !== this.lastAllowed) {
      this.lastAllowed = allowed;
      this.updateUI();
    }
    if (!this.is040Active() && this.active) this.disable();
    if (this.spot === "polo-ii" && this.is040Active() && this.requested &&
        !this.active && !this.loading && !this.warning) void this.refresh();
  }

  metrics(): VegetationQAReceipt {
    const count = (key: "sourceTriangles" | "hiddenTriangles" | "keptTriangles") =>
      this.sources.reduce((sum, v) => sum + v[key], 0);
    return {
      active: this.active,
      enabled: this.requested,
      pending: this.loading,
      spot: this.spot,
      allowed: this.spot === "polo-ii" && this.is040Active(),
      matchedSourceMeshes: this.sources.length,
      selectedCrowns: this.sources.reduce((sum, v) => sum + v.crowns.length, 0),
      hiddenSourceTriangles: count("hiddenTriangles"),
      retainedSourceTriangles: count("keptTriangles"),
      lobeInstances: this.lobeInstances,
      originalGeometryRestored: this.sources.every(v =>
        v.mesh.geometry === (this.active ? v.filtered : v.original)),
      sceneGeometrySource: "accepted Coimbra 032/037 GLB semantic vegetation",
      crop_m: [HALF_WIDTH * 2, HALF_WIDTH * 2],
      margin_m: INNER_MARGIN,
      originalGLBModified: false,
      ...(this.warning ? { warning: this.warning } : {}),
    };
  }

  private updateUI() {
    const available = this.spot === "polo-ii" && this.is040Active();
    this.button.disabled = !available || this.loading;
    this.button.textContent = this.active ? "Trees: original" : "Trees: smoother 041";
    this.status.textContent = this.loading ? "Reading original vegetation crowns…" :
      this.active ? ("041 vegetation · " + this.metrics().selectedCrowns +
        " accepted crowns · " + this.lobeInstances + " smooth lobes") :
      (available ? "040 vegetation baseline · 041 candidate disabled" :
        "041 trees available only with Polo II visual candidate");
    if (this.warning) this.status.textContent += " · " + this.warning;
  }

  private disable() {
    for (const item of this.sources) item.mesh.geometry = item.original;
    this.group.visible = false;
    this.active = false;
    this.updateUI();
  }

  private async build() {
    if (this.built) return;
    this.source.updateMatrixWorld(true);
    const items = getAcceptedSources(this.source);
    if (items.length < 3) throw new Error("Original semantic tree meshes unavailable");
    const sources = items.map(item => analyseMesh(item.mesh, item.material));
    const total = sources.reduce((sum, v) => sum + v.crowns.length, 0);
    if (total < 15 || total > MAX_CROWNS) {
      throw new Error("Unexpected accepted Polo II crown count: " + total);
    }
    const group = new THREE.Group();
    for (const item of sources) {
      const smooth = createLobes(item);
      if (smooth) {
        group.add(smooth);
        this.lobeInstances += smooth.count;
      }
    }
    this.group.add(group);
    this.scene.add(this.group);
    this.sources = sources;
    this.built = true;
  }

  private async refresh() {
    if (!this.requested || this.spot !== "polo-ii" || !this.is040Active()) {
      this.disable();
      return;
    }
    if (this.active || this.loading) return;
    this.loading = true;
    this.warning = undefined;
    this.updateUI();
    try {
      await this.build();
      if (!this.requested || this.spot !== "polo-ii" || !this.is040Active()) return;
      for (const item of this.sources) item.mesh.geometry = item.filtered;
      this.group.visible = true;
      this.active = true;
    } catch (err) {
      this.warning = String(err);
      this.disable();
    } finally {
      this.loading = false;
      this.updateUI();
    }
  }
}
