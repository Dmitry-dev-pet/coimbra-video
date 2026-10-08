#!/usr/bin/env python3
from __future__ import annotations

import functools
import http.server
import json
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path


# The caller's execution workspace, not the installed project package directory.
ROOT = Path.cwd()
SITE = ROOT / "site"
OUT_DIR = ROOT / "artifacts" / "coimbra-034"
RECEIPT = OUT_DIR / "benchmark.json"
BROWSER_LOG = OUT_DIR / "browser.log"

BROWSER_CANDIDATES = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
]


def resolve_browser() -> Path:
    for candidate in BROWSER_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "No approved Chromium-family browser found in fixed /Applications paths"
    )


class ReceiptHandler(http.server.SimpleHTTPRequestHandler):
    receipt_event: threading.Event

    def log_message(self, format: str, *args) -> None:
        return

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/__coimbra034_benchmark":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ValueError("invalid receipt size")
            payload = json.loads(self.rfile.read(length))
            RECEIPT.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            self.send_error(400, f"invalid receipt: {type(exc).__name__}")
            return

        self.send_response(204)
        self.end_headers()
        self.receipt_event.set()


def validate_receipt(payload: dict, browser: Path, version: str) -> dict:
    if payload.get("lane") != "coimbra-034-webgpu-feasibility":
        raise ValueError("unexpected lane")
    if payload.get("automation") != "mac-access-headless-preflight":
        raise ValueError("unexpected automation mode")
    if payload.get("route_contract") != "COIMBRA-BRIDGE-003-SLOW":
        raise ValueError("unexpected route contract")
    if payload.get("route_anchors") != 7:
        raise ValueError("unexpected route anchor count")

    adapter = payload.get("adapter") or {}
    benchmark = payload.get("benchmark") or {}

    if adapter.get("available") is not True:
        raise ValueError("WebGPU adapter unavailable")
    if benchmark.get("webgpu_available") is not True:
        raise ValueError("navigator.gpu unavailable")
    if benchmark.get("mode") != "scripted route":
        raise ValueError("benchmark did not remain in scripted route mode")

    sample_count = int(benchmark.get("sample_count") or 0)
    if sample_count < 300:
        raise ValueError(f"too few frame samples: {sample_count}")

    p50 = float(benchmark.get("p50_frame_ms") or 0)
    p95 = float(benchmark.get("p95_frame_ms") or 0)
    long_frames = int(benchmark.get("frames_over_50ms") or 0)

    target_met = p50 <= 16.7 and p95 <= 22.0 and long_frames == 0

    payload["mac_preflight"] = {
        "browser_binary": str(browser),
        "browser_version": version,
        "headless": True,
        "window_css_target": [1440, 900],
        "device_scale_factor_requested": 2,
        "renderer_pixel_ratio_cap": 1.5,
        "target": {
            "p50_frame_ms_lte": 16.7,
            "p95_frame_ms_lte": 22.0,
            "frames_over_50ms": 0,
        },
        "target_met": target_met,
        "acceptance": "automated_preflight_only",
    }
    return payload


def main() -> int:
    required = [
        SITE / "index.html",
        SITE / "data" / "coimbra" / "index.json",
    ]
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"Missing fixed Coimbra 034 site input: {path}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPT.unlink(missing_ok=True)

    browser = resolve_browser()
    version_run = subprocess.run(
        [str(browser), "--version"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=15,
    )
    version = version_run.stdout.strip().splitlines()[0] if version_run.stdout else "unknown"

    event = threading.Event()
    ReceiptHandler.receipt_event = event
    handler = functools.partial(ReceiptHandler, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}/?autobenchmark=1"

    browser_process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="coimbra034-chrome-") as profile:
            with BROWSER_LOG.open("w", encoding="utf-8") as log:
                command = [
                    str(browser),
                    "--headless=new",
                    "--enable-gpu",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--window-size=1440,900",
                    "--force-device-scale-factor=2",
                    f"--user-data-dir={profile}",
                    url,
                ]
                browser_process = subprocess.Popen(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if event.wait(timeout=1):
                        break
                    code = browser_process.poll()
                    if code is not None:
                        raise RuntimeError(f"browser exited early with code {code}")
                else:
                    raise TimeoutError("timed out waiting for 65-second WebGPU receipt")
    finally:
        server.shutdown()
        server.server_close()
        if browser_process is not None and browser_process.poll() is None:
            browser_process.terminate()
            try:
                browser_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                browser_process.kill()
                browser_process.wait(timeout=10)

    if not RECEIPT.is_file():
        detail = BROWSER_LOG.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise SystemExit("Browser produced no receipt. Tail:\n" + detail)

    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    verified = validate_receipt(payload, browser, version)
    RECEIPT.write_text(
        json.dumps(verified, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    safe = {
        "adapter": verified.get("adapter"),
        "benchmark": verified.get("benchmark"),
        "mac_preflight": verified.get("mac_preflight"),
        "route_contract": verified.get("route_contract"),
        "route_anchors": verified.get("route_anchors"),
    }
    print(json.dumps(safe, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
