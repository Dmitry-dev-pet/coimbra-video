from __future__ import annotations

import getpass
import json
import os
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
RAW = ROOT / "data" / "raw" / "mds_bridge"

MAIN = "https://cdd.dgterritorio.gov.pt"
AUTH_BASE = "https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect"
REDIRECT_URI = "https://cdd.dgterritorio.gov.pt/auth/callback"
CLIENT_ID = "aai-oidc-dgt"
STAC_SEARCH = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"
COLLECTION = "MDS-2m"


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_login = False
        self.action = None
        self.hidden: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "form" and data.get("id") == "kc-form-login":
            self.in_login = True
            self.action = data.get("action")
        elif self.in_login and tag == "input":
            if data.get("type") == "hidden" and data.get("name"):
                self.hidden[data["name"]] = data.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form" and self.in_login:
            self.in_login = False


def authenticate(user: str, password: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "apatch-blender-coimbra-demo/0.3",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        }
    )

    session.get(MAIN, timeout=30).raise_for_status()
    response = session.get(
        f"{AUTH_BASE}/auth",
        params={
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": "openid profile email",
        },
        timeout=30,
    )
    response.raise_for_status()

    parser = LoginForm()
    parser.feed(response.text)
    if not parser.action:
        raise RuntimeError("Could not locate DGT/Keycloak login form")

    payload = dict(parser.hidden)
    payload.update({"username": user, "password": password})
    action = urljoin(response.url, parser.action)
    response = session.post(action, data=payload, allow_redirects=True, timeout=60)
    response.raise_for_status()
    return session


def latest_only(features: list[dict]) -> list[dict]:
    picked: dict[str, tuple[int, dict]] = {}
    for feature in features:
        fid = feature.get("id", "")
        base = re.sub(r"_v\d+$", "", fid)
        match = re.search(r"_v(\d+)$", fid)
        version = int(match.group(1)) if match else 0
        old = picked.get(base)
        if old is None or version > old[0]:
            picked[base] = (version, feature)
    return [item[1] for item in picked.values()]


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    bbox = cfg["bbox_wgs84"]

    user = os.getenv("DGT_USER") or input("DGT CDD email: ").strip()
    password = os.getenv("DGT_PASSWORD") or getpass.getpass("DGT CDD password: ")
    if not user or not password:
        raise SystemExit("DGT_USER and DGT_PASSWORD are required")

    session = authenticate(user, password)
    payload = {"bbox": bbox, "limit": 1000, "collections": [COLLECTION]}
    response = session.post(STAC_SEARCH, json=payload, timeout=90)
    response.raise_for_status()
    features = latest_only(response.json().get("features", []))
    if not features:
        raise SystemExit(f"No {COLLECTION} tiles found for {bbox}")

    assets = []
    for feature in features:
        for asset in feature.get("assets", {}).values():
            href = asset.get("href")
            ctype = (asset.get("type") or "").lower()
            if href and ("tiff" in ctype or href.lower().split("?")[0].endswith((".tif", ".tiff"))):
                assets.append((feature.get("id", "tile"), href))
                break

    RAW.mkdir(parents=True, exist_ok=True)
    print(f"{len(assets)} DGT {COLLECTION} tiles intersect bridge bbox")

    for index, (feature_id, href) in enumerate(assets, start=1):
        name = Path(href.split("?")[0]).name
        if not name.lower().endswith((".tif", ".tiff")):
            name = f"{feature_id}.tif"
        output = RAW / name
        if output.exists() and output.stat().st_size > 0:
            print(f"[{index}/{len(assets)}] exists {output.name}")
            continue

        last_error = None
        for attempt in range(1, 4):
            try:
                print(f"[{index}/{len(assets)}] download {output.name}, attempt {attempt}")
                with session.get(href, stream=True, timeout=240) as download:
                    download.raise_for_status()
                    ctype = download.headers.get("content-type", "").lower()
                    if "text/html" in ctype:
                        raise RuntimeError("DGT returned HTML instead of GeoTIFF")
                    with output.open("wb") as handle:
                        for chunk in download.iter_content(1024 * 1024):
                            if chunk:
                                handle.write(chunk)
                break
            except Exception as exc:
                last_error = exc
                if output.exists():
                    output.unlink()
                time.sleep(attempt * 3)
        else:
            raise RuntimeError(f"Failed {output.name}: {last_error!r}")

    print(f"Raw bridge MDS tiles: {RAW}")


if __name__ == "__main__":
    main()
