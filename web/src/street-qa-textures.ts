import * as THREE from "three/webgpu";

/**
 * WebGPU QA fixture for software adapters whose maxTextureDimension2D is 8192.
 *
 * The accepted source GLB is untouched. Only the decoded, in-memory source of
 * oversized browser textures is resized before first rendering, and only
 * when the user explicitly requests the diagnostic ?streetQA=... mode.
 */
export function fitStreetQATextures(
  source: THREE.Object3D,
  maxDimension = 8192,
): { resized: number; images: { original: [number, number]; adapted: [number, number] }[] } {
  if (!Number.isInteger(maxDimension) || maxDimension < 1024) {
    throw new Error("Invalid Street QA texture limit");
  }
  const textures = new Set<THREE.Texture>();
  source.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh) return;
    const allMaterials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const material of allMaterials) {
      if (!material) continue;
      for (const value of Object.values(material)) {
        if (value && typeof value === "object" && (value as THREE.Texture).isTexture) {
          textures.add(value as THREE.Texture);
        }
      }
    }
  });

  const images: { original: [number, number]; adapted: [number, number] }[] = [];
  for (const texture of textures) {
    const img = texture.image as (CanvasImageSource & { width?: number; height?: number }) | undefined;
    if (!img || !img.width || !img.height) continue;
    const width = img.width, height = img.height;
    if (Math.max(width, height) <= maxDimension) continue;
    const scale = maxDimension / Math.max(width, height);
    const newWidth = Math.max(1, Math.floor(width * scale));
    const newHeight = Math.max(1, Math.floor(height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = newWidth;
    canvas.height = newHeight;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Street QA texture resizing unavailable");
    context.drawImage(img, 0, 0, newWidth, newHeight);
    texture.image = canvas;
    texture.needsUpdate = true;
    images.push({ original: [width, height], adapted: [newWidth, newHeight] });
  }
  source.userData.coimbra039TextureQA = {
    maxDimension,
    resized: images.length,
    images,
    limitation: "Runtime-only texture downsampling for software GPU; original accepted GLB unchanged",
  };
  return { resized: images.length, images };
}
