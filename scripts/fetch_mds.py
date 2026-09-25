from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests

from common import RAW_MDS, ensure_dirs, load_config

MAIN = "https://cdd.dgterritorio.gov.pt"
AUTH_BASE = "https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect"
REDIRECT_URI = "https://cdd.dgterritorio.gov.pt/auth/callback"
CLIENT_ID = "aai-oidc-dgt"
STAC_SEARCH = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"
DEFAULT_COLLECTION = "MDS-50cm"

class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_login = False
        self.action = None
        self.hidden: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "form" and d.get("id") == "kc-form-login":
            self.in_login = True
            self.action = d.get("action")
        elif self.in_login and tag == "input":
            if d.get("type") == "hidden" and d.get("name"):
                self.hidden[d["name"]] = d.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form" and self.in_login:
            self.in_login = False

def authenticate(user: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "coimbra-dgt-prototype/0.1",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    })

    s.get(MAIN, timeout=30).raise_for_status()
    r = s.get(
        f"{AUTH_BASE}/auth",
        params={
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": "openid profile email",
        },
        timeout=30,
    )
    r.raise_for_status()

    parser = LoginForm()
    parser.feed(r.text)
    if not parser.action:
        raise RuntimeError("Could not locate the DGT/Keycloak login form.")

    payload = dict(parser.hidden)
    payload.update({"username": user, "password": password})
    action = urljoin(r.url, parser.action)
    r = s.post(action, data=payload, allow_redirects=True, timeout=60)
    r.raise_for_status()

    # Verify the authenticated browser session against the same endpoint we need.
    test = s.post(STAC_SEARCH, json={"bbox": [-8.44, 40.19, -8.41, 40.22], "limit": 1}, timeout=30)
    if test.status_code != 200:
        raise RuntimeError(
            f"DGT login did not produce a usable CDD session (HTTP {test.status_code})."
        )
    return s

def latest_only(features: list[dict]) -> list[dict]:
    # DGT may publish _v01, _v02... corrections. Keep newest version per base filename.
    picked: dict[str, tuple[int, dict]] = {}
    for f in features:
        fid = f.get("id", "")
        base = re.sub(r"_v\d+$", "", fid)
        m = re.search(r"_v(\d+)$", fid)
        version = int(m.group(1)) if m else 0
        old = picked.get(base)
        if old is None or version > old[0]:
            picked[base] = (version, f)
    return [x[1] for x in picked.values()]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ensure_dirs()
    cfg = load_config()
    bbox = cfg["bbox_wgs84"]

    user = os.getenv("DGT_USER") or input("DGT CDD email: ").strip()
    password = os.getenv("DGT_PASSWORD") or getpass.getpass("DGT CDD password: ")

    s = authenticate(user, password)
    print("Authenticated.")

    payload = {"bbox": bbox, "limit": 1000, "collections": [args.collection]}
    r = s.post(STAC_SEARCH, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    features = latest_only(data.get("features", []))

    if not features:
        raise SystemExit(
            f"No '{args.collection}' tiles found for bbox {bbox}. "
            "Check DGT coverage or try --collection MDS-2m."
        )

    assets = []
    for f in features:
        for asset in f.get("assets", {}).values():
            href = asset.get("href")
            ctype = (asset.get("type") or "").lower()
            if href and ("tiff" in ctype or href.lower().endswith((".tif", ".tiff"))):
                assets.append((f.get("id", "tile"), href))
                break

    print(f"{len(assets)} {args.collection} GeoTIFF tile(s) intersect the test bbox.")
    if args.dry_run:
        for fid, href in assets:
            print(" ", fid, href)
        return

    for i, (fid, href) in enumerate(assets, 1):
        name = Path(href.split("?")[0]).name
        if not name.lower().endswith((".tif", ".tiff")):
            name = f"{fid}.tif"
        out = RAW_MDS / name
        if out.exists() and out.stat().st_size > 0:
            print(f"[{i}/{len(assets)}] exists: {out.name}")
            continue

        print(f"[{i}/{len(assets)}] downloading {out.name}")
        with s.get(href, stream=True, timeout=180) as rr:
            rr.raise_for_status()
            ctype = rr.headers.get("content-type", "").lower()
            if "text/html" in ctype:
                raise RuntimeError("CDD returned HTML instead of GeoTIFF; session may have expired.")
            with out.open("wb") as fh:
                for chunk in rr.iter_content(1024 * 1024):
                    if chunk:
                        fh.write(chunk)

    print(f"Raw MDS tiles: {RAW_MDS}")

if __name__ == "__main__":
    main()
