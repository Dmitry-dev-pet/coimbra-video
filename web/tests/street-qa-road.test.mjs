import test from "node:test";
import assert from "node:assert/strict";
import { projectToRoad } from "../src/street-qa-road.ts";

const spot = {
  label: "Sanches / Brasil",
  anchor: [-293.37, 851.60],
  toward: [-692.18, 331.73],
};

test("snaps to the closest point on an eligible OSM street", () => {
  const result = projectToRoad(spot, [
    { kind: "local", a: [-294, 840, 0], b: [-294, 860, 0] },
    { kind: "major", a: [-400, 800, 0], b: [-400, 860, 0] },
  ]);
  assert.equal(result.roadKind, "local");
  assert.ok(Math.abs(result.roadDistance - 0.63) < 1e-8);
  assert.ok(result.forwardNorth < 0); // toward the original Coimbra 010 target
  assert.ok(Math.abs(result.x - (-293.15)) < 1e-8);
  assert.ok(Math.abs(result.north - 851.60) < 1e-8);
});

test("ignores paths and degenerate segments", () => {
  const result = projectToRoad(spot, [
    { kind: "paths", a: [-293.37, 840, 0], b: [-293.37, 860, 0] },
    { kind: "local", a: [-293.37, 851.6, 0], b: [-293.37, 851.6, 0] },
    { kind: "service", a: [-297, 840, 0], b: [-297, 860, 0] },
  ]);
  assert.equal(result.roadKind, "service");
  assert.ok(result.roadDistance > 3);
});

test("rejects anchors with no verifiable nearby street", () => {
  assert.throws(() => projectToRoad(spot, []), /No verified OSM road/);
  assert.throws(() => projectToRoad(spot, [
    { kind: "local", a: [500, 500, 0], b: [600, 600, 0] },
  ]), /80 m/);
});

test("orientation follows intended direction, offset remains 0.85 m", () => {
  const p = { label: "test", anchor: [5, 1], toward: [5, -10] };
  const result = projectToRoad(p, [
    { kind: "local", a: [0, 0, 0], b: [10, 0, 0] },
  ]);
  assert.equal(result.forwardX, 1); // direction is orthogonal: original order stays
  assert.equal(result.forwardNorth, 0);
  assert.equal(result.north, 0.85);
  assert.equal(result.x, 5);
});

test("projection clamps to road endpoints, not imaginary extended lines", () => {
  const p = { label: "end", anchor: [20, 4], toward: [-1, 4] };
  const result = projectToRoad(p, [
    { kind: "local", a: [0, 0, 0], b: [10, 0, 0] },
  ]);
  assert.ok(Math.abs(result.roadDistance - Math.hypot(10, 4)) < 1e-8);
  assert.equal(result.forwardX, -1);
});
