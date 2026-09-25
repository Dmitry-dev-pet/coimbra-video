# Coimbra Video

Current direction: **Google Earth Studio → tilt-shift post-processing → MP4**.

The earlier DGT/LiDAR experiment is kept in the repository as a fallback, but it is no longer the main path.

## Why this path

Google Earth Studio already provides the realistic 3D city imagery and cinematic camera system. We use it only as the source renderer, then do our own miniature/tilt-shift look afterwards.

The post-processing stage:
- keeps the original Earth Studio framing;
- never crops the image;
- applies a tilted focus band;
- progressively blurs foreground/background;
- adds a small saturation/contrast lift;
- explicitly protects the bottom attribution area from blur;
- encodes the final H.264 MP4.

## 1. Create the Coimbra shot

See [EARTH_STUDIO.md](EARTH_STUDIO.md).

Recommended first test:
- search for **Universidade de Coimbra**;
- 10–12 seconds;
- 30 fps;
- 1920×1080;
- slow oblique orbit/lateral move;
- University + Baixa + Mondego in frame;
- render an image sequence ZIP;
- leave Earth Studio attribution visible.

Official Earth Studio:
https://earth.google.com/studio/

## 2. Process locally

Install Python dependencies and ffmpeg:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then:

```bash
python scripts/earth_studio_post.py \
  --input ~/Downloads/earth-studio-render.zip \
  --output output/coimbra_earthstudio_tiltshift.mp4 \
  --fps 30
```

Main controls:

```text
--focus-y       vertical position of the sharp band
--tilt          slope of the sharp band
--sharp-width   width of the fully sharp zone
--blur-span     how quickly blur grows away from focus
--max-radius    maximum Gaussian blur radius
```

## 3. Process in GitHub Actions

Open:

**Actions → Coimbra Earth Studio post-process → Run workflow**

Provide:
- `source_url`: a **direct downloadable URL** to the ZIP exported by Earth Studio;
- `fps`: the same frame rate as the Earth Studio project;
- optional `focus_y` and `tilt`.

The result appears under the workflow run in:

**Artifacts → coimbra-earthstudio-video**

and contains:

```text
coimbra_earthstudio_tiltshift.mp4
```

A normal Google Drive sharing page is not a direct file URL. For Actions, use a URL that returns the ZIP bytes directly.

## Attribution

Do not crop, hide, replace or remove Google Earth / imagery-provider attribution.

Earth Studio automatically generates attribution for rendered frames. The post-processing script preserves the bottom part of every original frame so the credits remain readable.

Official attribution documentation:
https://earth.google.com/studio/docs/attribution/

## Legacy DGT experiment

The original open-data experiment remains available:
- DGT 2025 orthophoto downloader;
- DGT MDS/LiDAR downloader;
- mesh builder;
- Blender preview.

Those files are retained as a fallback, not used by the main GitHub Action.
