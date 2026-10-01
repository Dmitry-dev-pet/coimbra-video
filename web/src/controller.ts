import * as THREE from "three/webgpu";
import type { RouteAnchor } from "./types";

function toThree(point: [number, number, number]) {
  return new THREE.Vector3(point[0], point[2], -point[1]);
}

export class CameraController {
  private readonly keys = new Set<string>();
  private dragging = false;
  private lastX = 0;
  private lastY = 0;
  private yaw = 0;
  private pitch = -0.25;
  private routeMode = true;
  private routeClock = 0;
  private readonly routeDuration: number;
  private readonly positionCurve: THREE.CatmullRomCurve3;
  private readonly targetCurve: THREE.CatmullRomCurve3;

  constructor(
    private readonly camera: THREE.PerspectiveCamera,
    private readonly element: HTMLElement,
    anchors: RouteAnchor[],
    durationSeconds: number,
  ) {
    if (anchors.length < 2) {
      throw new Error("Coimbra route requires at least two anchors");
    }
    this.routeDuration = Math.max(1, durationSeconds);
    this.positionCurve = new THREE.CatmullRomCurve3(
      anchors.map((anchor) => toThree(anchor.location)),
      false,
      "centripetal",
    );
    this.targetCurve = new THREE.CatmullRomCurve3(
      anchors.map((anchor) => toThree(anchor.target)),
      false,
      "centripetal",
    );

    this.camera.position.copy(toThree(anchors[0].location));
    this.camera.lookAt(toThree(anchors[0].target));
    this.syncFreeAngles();

    addEventListener("keydown", (event) => {
      if (event.code === "KeyP" && !event.repeat) {
        this.routeMode = !this.routeMode;
        if (!this.routeMode) this.syncFreeAngles();
        return;
      }
      this.keys.add(event.code);
      if (["KeyW", "KeyA", "KeyS", "KeyD", "KeyQ", "KeyE"].includes(event.code)) {
        if (this.routeMode) {
          this.routeMode = false;
          this.syncFreeAngles();
        }
      }
    });
    addEventListener("keyup", (event) => this.keys.delete(event.code));

    element.addEventListener("pointerdown", (event) => {
      this.dragging = true;
      this.lastX = event.clientX;
      this.lastY = event.clientY;
      element.setPointerCapture(event.pointerId);
      if (this.routeMode) {
        this.routeMode = false;
        this.syncFreeAngles();
      }
    });
    element.addEventListener("pointerup", (event) => {
      this.dragging = false;
      element.releasePointerCapture(event.pointerId);
    });
    element.addEventListener("pointermove", (event) => {
      if (!this.dragging) return;
      const dx = event.clientX - this.lastX;
      const dy = event.clientY - this.lastY;
      this.lastX = event.clientX;
      this.lastY = event.clientY;
      this.yaw -= dx * 0.003;
      this.pitch -= dy * 0.003;
      this.pitch = THREE.MathUtils.clamp(this.pitch, -1.45, 1.45);
      this.applyFreeRotation();
    });
  }

  private syncFreeAngles() {
    const euler = new THREE.Euler().setFromQuaternion(this.camera.quaternion, "YXZ");
    this.pitch = euler.x;
    this.yaw = euler.y;
  }

  private applyFreeRotation() {
    this.camera.rotation.set(this.pitch, this.yaw, 0, "YXZ");
  }

  update(dt: number) {
    if (this.routeMode) {
      this.routeClock = (this.routeClock + dt) % this.routeDuration;
      const t = this.routeClock / this.routeDuration;
      this.camera.position.copy(this.positionCurve.getPointAt(t));
      this.camera.lookAt(this.targetCurve.getPointAt(t));
      return true;
    }

    const speed = (this.keys.has("ShiftLeft") || this.keys.has("ShiftRight")) ? 180 : 70;
    const step = speed * dt;
    const forward = new THREE.Vector3(Math.sin(this.yaw), 0, -Math.cos(this.yaw));
    const right = new THREE.Vector3(Math.cos(this.yaw), 0, Math.sin(this.yaw));
    const move = new THREE.Vector3();

    if (this.keys.has("KeyW")) move.add(forward);
    if (this.keys.has("KeyS")) move.sub(forward);
    if (this.keys.has("KeyD")) move.add(right);
    if (this.keys.has("KeyA")) move.sub(right);
    if (this.keys.has("KeyE")) move.y += 1;
    if (this.keys.has("KeyQ")) move.y -= 1;

    if (move.lengthSq() > 0) {
      move.normalize().multiplyScalar(step);
      this.camera.position.add(move);
      this.camera.position.y = Math.max(4, this.camera.position.y);
      this.applyFreeRotation();
      return true;
    }
    return false;
  }

  mode() {
    return this.routeMode ? "scripted route" : "free flight";
  }
}
