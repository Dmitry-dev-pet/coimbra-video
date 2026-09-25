# Coimbra DGT miniature — first data-quality prototype

Goal: test one thing only — whether the **official DGT 2024/2025 surface model + 2025 25 cm orthophoto**
can produce a convincing photographic miniature view of central Coimbra.

This is deliberately **not** a Three.js project yet.

## Test area

The default crop is about **2.4 × 2.0 km** and covers the University / Baixa / Mondego corridor.

- WGS84 bbox: `-8.4400546, 40.1989577, -8.4119417, 40.2170406`
- PT-TM06 / ETRS89 (EPSG:3763): `-26135.114, 58970.521, -23735.114, 60970.521`

## Official sources

### Surface model

DGT LiDAR survey:
- `MDS-50cm` — Digital Surface Model, 0.5 m pixels
- CRS: EPSG:3763
- source survey: 2024–2025
- download requires a free CDD account

CDD:
https://cdd.dgterritorio.gov.pt/

### Orthophoto

DGT orthophoto 2025:
- RGB + NIR
- 25 cm GSD
- WMS layer: `Ortos2025-RGB`
- WMS: `https://cartografia.dgterritorio.gov.pt/wms/ortos2025`
- CRS: EPSG:3763

## Why MDS and not MDT?

For this visual test we need roofs and tree canopies. `MDS-50cm` contains surface objects;
`MDT-50cm` is bare earth.

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Fetch orthophoto

No login is required for the WMS:

```bash
python scripts/fetch_ortho.py
```

Expected output:

```text
data/processed/ortho_2025.tif
data/processed/ortho_2025.jpg
```

The downloader tiles the request so the 25 cm source is not silently reduced by a WMS image-size limit.

### 2. Fetch DGT MDS-50cm

Create a free CDD account first. Credentials are read interactively and are **not written to disk**:

```bash
python scripts/fetch_mds.py
```

Or:

```bash
DGT_USER="you@example.com" python scripts/fetch_mds.py
```

The password is still requested with `getpass()`.

Raw GeoTIFF tiles go to:

```text
data/raw/mds/
```

### 3. Mosaic/crop the MDS

```bash
python scripts/prepare_mds.py
```

Output:

```text
data/processed/mds_50cm.tif
```

### 4. Build a render mesh

The source remains 50 cm, but the MVP mesh defaults to 2 m to keep Blender light.

```bash
python scripts/build_mesh.py --mesh-resolution 2.0
```

Outputs:

```text
data/processed/coimbra.obj
data/processed/coimbra.mtl
data/processed/ortho_2025.jpg
```

### 5. Render in Blender

If Blender is installed:

```bash
blender -b -P blender/render_scene.py
```

Output:

```text
output/coimbra_sharp.png
```

### 6. Apply miniature / tilt-shift look

For this *first* source-quality test the focus band is intentionally a simple image-space
tilted band. If the DGT data passes the visual test, replace it with the final
depth/world-space tilted focal plane.

```bash
python scripts/tiltshift.py
```

Output:

```text
output/coimbra_tiltshift.png
```

## One-command sequence

```bash
make ortho
make mds
make prepare
make mesh
make render
make tiltshift
```

## Important

The first question is not “is the tilt-shift shader perfect?” It is:

> When the 25 cm aerial photograph is draped over a surface model that actually contains
> Coimbra's roofs, trees and terrain, does the scene already read as a photograph rather than a GIS model?

If yes, we continue to the real depth-based focus plane and camera animation.
If no, we stop before building any cinematic engine.

## Attribution

Keep DGT attribution in any published output. See `SOURCES.md`.


## GitHub Actions

The repository includes `.github/workflows/preview.yml`.

Open **Actions → Coimbra DGT preview → Run workflow**.

Without secrets, the workflow still:
1. validates the project;
2. downloads the public DGT 2025 orthophoto;
3. uploads `coimbra-orthophoto-2025` as an artifact.

For the complete MDS → mesh → Blender → tilt-shift preview, add these repository
secrets under **Settings → Secrets and variables → Actions**:

- `DGT_USER`
- `DGT_PASSWORD`

Do not commit DGT credentials to the repository.

The workflow has a `mesh_resolution` input:
- `4.0` m — quick/cheap preview;
- `2.0` m — default quality test;
- `1.0` m — heavier experiment.

The original MDS remains 0.5 m; this input only controls the render mesh density.
