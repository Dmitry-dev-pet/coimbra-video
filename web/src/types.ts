export interface RouteAnchor {
  frame: number;
  location: [number, number, number];
  target: [number, number, number];
  lens: number;
}

export interface TileIndexEntry {
  i: number;
  j: number;
  top: number;
  path: string;
}

export interface CityIndex {
  schema_version: number;
  lane: string;
  tile_size: number;
  bounds_local: [number, number, number, number];
  terrain: {
    source: string;
    resolution_m: number;
    z0: number;
    bbox_wgs84?: [number, number, number, number];
  };
  city: {
    source: string;
    attribution: string;
  };
  route: {
    source_contract: string;
    duration_seconds: number;
    anchors: RouteAnchor[];
  };
  tiles: TileIndexEntry[];
}

export interface BuildingData {
  id: number;
  polygon: [number, number][];
  base: number;
  height: number;
}

export interface RoadSegment {
  kind: "major" | "local" | "service" | "paths";
  a: [number, number, number];
  b: [number, number, number];
}

export interface TileData {
  i: number;
  j: number;
  terrain: null | {
    xs: number[];
    ys: number[];
    heights: number[][];
  };
  buildings: BuildingData[];
  roads: RoadSegment[];
}
