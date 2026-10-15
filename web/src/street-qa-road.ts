// Pure street-to-road geometry, kept independent of Three.js for cheap Node tests.
// Inputs use the local Coimbra EPSG:3763-relative XY coordinate convention.

export type StreetAnchor = {
  label: string;
  anchor: readonly [number, number];
  toward: readonly [number, number];
};

export type RoadInput = {
  kind: string;
  a: readonly [number, number, number];
  b: readonly [number, number, number];
};

export type StreetLocation = {
  x: number;
  north: number;
  forwardX: number;
  forwardNorth: number;
  roadDistance: number;
  roadKind: string;
};

export function projectToRoad(
  spot: StreetAnchor,
  roads: readonly RoadInput[],
  maxDistance = 80,
): StreetLocation {
  const ax = spot.anchor[0], ay = spot.anchor[1];
  let best: StreetLocation | null = null;

  for (const road of roads) {
    if (road.kind === "paths") continue; // 010 QA used drivable road segments
    const [x0, y0] = road.a, [x1, y1] = road.b;
    const dx = x1 - x0, dy = y1 - y0;
    const len2 = dx * dx + dy * dy;
    if (len2 < 0.01) continue;

    const u = Math.max(0, Math.min(1, ((ax - x0) * dx + (ay - y0) * dy) / len2));
    const px = x0 + dx * u, py = y0 + dy * u;
    const roadDistance = Math.hypot(px - ax, py - ay);
    if (best && roadDistance >= best.roadDistance) continue;

    const inv = 1 / Math.sqrt(len2);
    let forwardX = dx * inv, forwardNorth = dy * inv;
    const desiredX = spot.toward[0] - ax, desiredY = spot.toward[1] - ay;
    if (forwardX * desiredX + forwardNorth * desiredY < 0) {
      forwardX = -forwardX;
      forwardNorth = -forwardNorth;
    }

    best = {
      x: px - forwardNorth * 0.85,
      north: py + forwardX * 0.85,
      forwardX,
      forwardNorth,
      roadDistance,
      roadKind: road.kind,
    };
  }

  if (!best || best.roadDistance > maxDistance) {
    throw new Error("No verified OSM road within " + maxDistance + " m of " + spot.label);
  }
  return best;
}
