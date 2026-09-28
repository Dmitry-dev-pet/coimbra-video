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
RAW_ROOT = ROOT / "data" / "raw" / "dgt_highres"

MAIN = "https://cdd.dgterritorio.gov.pt"
AUTH_BASE = "https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect"
REDIRECT_URI = "https://cdd.dgterritorio.gov.pt/auth/callback"
CLIENT_ID = "aai-oidc-dgt"
STAC_SEARCH = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"
COLLECTIONS = ("MDT-50cm", "MDS-50cm")


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
            "User-Agent": "coimbra-video/008-highres (+https://github.com/Dmitry-dev-pet/coimbra-video)",
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

    test = session.post(
        STAC_SEARCH,
        json={"bbox": [-8.4235, 40.1833, -8.402, 40.2035], "limit": 1},
        timeout=30,
    )
    if test.status_code != 200:
        raise RuntimeError(
            f"DGT login did not produce a usable CDD session (HTTP {test.status_code})"
        )
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


def geotiff_asset(feature: dict):
    for asset in feature.get("assets", {}).values():
        href = asset.get("href")
        ctype = (asset.get("type") or "").lower()
        clean = href.lower().split("?")[0] if href else ""
        if href and ("tiff" in ctype or clean.endswith((".tif", ".tiff"))):
            return href
    return None


def download_collection(session: requests.Session, collection: str, bbox: list[float]):
    response = session.post(
        STAC_SEARCH,
        json={"bbox": bbox, "limit": 1000, "collections": [collection]},
        timeout=90,
    )
    response.raise_for_status()
    features = latest_only(response.json().get("features", []))
    assets = []
    for feature in features:
        href = geotiff_asset(feature)
        if href:
            assets.append((feature.get("id", "tile"), href))

    if not assets:
        raise RuntimeError(f"No {collection} GeoTIFF tiles found for {bbox}")

    out_dir = RAW_ROOT / collection.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence = []

    for index, (feature_id, href) in enumerate(assets, start=1):
        name = Path(href.split("?")[0]).name
        if not name.lower().endswith((".tif", ".tiff")):
            name = f"{feature_id}.tif"
        output = out_dir / name

        if output.exists() and output.stat().st_size > 0:
            print(f"{collection} [{index}/{len(assets)}] exists {output.name}")
        else:
            last_error = None
            for attempt in range(1, 4):
                try:
                    print(
                        f"{collection} [{index}/{len(assets)}] download "
                        f"{output.name}, attempt {attempt}"
                    )
                    with session.get(href, stream=True, timeout=300) as download:
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
                    output.unlink(missing_ok=True)
                    time.sleep(attempt * 3)
            else:
                raise RuntimeError(f"Failed {output.name}: {last_error!r}")

        evidence.append(
            {
                "feature_id": feature_id,
                "file": output.relative_to(ROOT).as_posix(),
                "bytes": output.stat().st_size,
            }
        )

    return evidence


def anonymous_session_if_available(bbox: list[float]) -> requests.Session | None:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "coimbra-video/008-highres (+https://github.com/Dmitry-dev-pet/coimbra-video)",
            "Accept": "application/json,*/*",
        }
    )
    try:
        response = session.post(
            STAC_SEARCH,
            json={"bbox": bbox, "limit": 1, "collections": ["MDT-50cm"]},
            timeout=30,
        )
        if response.status_code != 200:
            print(f"Anonymous STAC unavailable: HTTP {response.status_code}")
            return None
        data = response.json()
        features = data.get("features", [])
        if not features:
            print("Anonymous STAC returned no features")
            return None

        href = geotiff_asset(features[0])
        if not href:
            print("Anonymous STAC returned no GeoTIFF asset")
            return None

        probe = session.get(href, stream=True, timeout=30)
        try:
            ctype = probe.headers.get("content-type", "").lower()
            if probe.status_code not in (200, 206) or "text/html" in ctype:
                print(
                    f"Anonymous asset probe unavailable: HTTP {probe.status_code}, "
                    f"content-type={ctype}"
                )
                return None
            next(probe.iter_content(64 * 1024), b"")
        finally:
            probe.close()

        print("Anonymous CDD/STAC GeoTIFF access is available.")
        return session
    except Exception as exc:
        print(f"Anonymous CDD probe failed: {exc!r}")
        return None


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    bbox = cfg["bbox_wgs84"]

    session = anonymous_session_if_available(bbox)
    access_mode = "anonymous"

    if session is None:
        access_mode = "authenticated"
        user = os.getenv("DGT_USER", "").strip()
        password = os.getenv("DGT_PASSWORD", "")
        if not user:
            try:
                user = input("DGT CDD email: ").strip()
            except EOFError:
                user = ""
        if not password and user:
            try:
                password = getpass.getpass("DGT CDD password: ")
            except (EOFError, KeyboardInterrupt):
                password = ""
        if not user or not password:
            raise SystemExit(
                "Anonymous CDD download is unavailable and DGT_USER / "
                "DGT_PASSWORD were not provided"
            )
        session = authenticate(user, password)
        print("Authenticated to DGT CDD.")

    manifest = {"bbox_wgs84": bbox, "access_mode": access_mode, "collections": {}}
    for collection in COLLECTIONS:
        manifest["collections"][collection] = download_collection(session, collection, bbox)

    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    path = RAW_ROOT / "download-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: len(v) for k, v in manifest["collections"].items()}, indent=2))


if __name__ == "__main__":
    main()
