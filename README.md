# Coimbra Video

Cinematic flyovers and miniature-style views of Coimbra, with inspectable source data, reproducible rendering and explicit scene-protection rules.

The project has **two complementary paths**, not one primary path and an abandoned fallback:

- **Blender / APatch:** an editable, reproducible city assembled from OSM geometry, DGT terrain/orthophotography and derived semantic detail. Governed source layers remain protected; renderer experiments are separate from geometry changes.
- **Google Earth Studio → post-processing:** realistic source imagery followed by controlled tilt-shift processing. Original framing and provider attribution must remain visible.

Read [AGENTS.md](AGENTS.md) before changing the project. Live branches, PRs, runs and artifacts are authoritative for execution status; a documented workflow is not proof that a render completed.

## Blender: find the right lane

| Lane | Purpose | Output / boundary |
| --- | --- | --- |
| 011–015 | Polo II photo patch, hero buildings and finishing | Isolated still-image experiments, not the whole-city scene |
| 016B–019 | Full route, roof audit and corrected pitched roofs | Full-city geometry and the native 360-frame route |
| 020 | Slow full-route EEVEE film with corrected roofs | 1,440 true Blender subframes, 48 s, 30 fps, 1280×720 |
| 021–023 | Semantic vegetation, undergrowth and verified objects | Evidence-gated scene details; QA candidates are not all promoted into geometry |
| 024–025 | EEVEE/Cycles comparison and checkpoint validation | Same scene/camera, paired frames 1, 181 and 360, 1600×1000 |
| 027 | Mac CPU/Metal checkpoint A/B | Frozen 026 scene; frames 1, 181 and 360; timing + pixel-difference evidence only |
| 028 | Mac Metal full-route acceptance | Frozen 026 scene; native 360 frames / 12 s / 1600×1000; Metal-only delivery with full receipts |
| 026 | Full native-route Cycles acceptance | 360 actual frames, 12 s, 30 fps, 1600×1000; render-only extension tracked in [PR #22](https://github.com/Dmitry-dev-pet/coimbra-video/pull/22) |

**020 and 026 are different deliveries.** The 48-second EEVEE version is preserved; the 12-second Cycles acceptance pass does not overwrite or silently retime it. Renderer promotion does not imply that all asset/geometry realism issues are solved.

Useful entry points:

- [020 smooth-route specification](docs/specs/SPEC-COIMBRA-SMOOTH-PITCHED-ROOFS-1.md) and [workflow](.github/workflows/coimbra-020-smooth-pitched-roofs.yml).
- [025 Cycles checkpoint specification](docs/specs/SPEC-COIMBRA-CYCLES-BASELINE-1.md) and [workflow](.github/workflows/coimbra-025-cycles-production-baseline.yml).
- [011–025 integration design and evidence rules](docs/INTEGRATION-011-025.md), implemented through [PR #23](https://github.com/Dmitry-dev-pet/coimbra-video/pull/23).
- [Actions runs and downloadable artifacts](https://github.com/Dmitry-dev-pet/coimbra-video/actions).

### Render acceptance

025 uses Cycles CPU with 16 samples, denoising and adaptive sampling while preserving the semantic scene, camera and route timing. The 026 extension checks its rebuilt scene against the accepted 025 manifest, freezes a packed scene, verifies hashes and camera poses around rendering, and validates the decoded MP4 and all shard receipts.

A completed delivery must have a successful final verifier and its actual MP4 artifact. Check the linked PR/run for live status; neither a submitted job nor successful unit tests alone establish video completion.

### Data and reproducibility

OSM footprints/roads provide geometry and semantics. DGT terrain, LiDAR derivatives and orthophotos provide terrain, height and imagery evidence. Packed textures and pinned derived inputs keep routine rendering separate from authenticated source acquisition. Do not confuse the ground sampling distance of source data with the output video resolution.

Some workflows consume **pinned Actions artifacts from earlier runs**. Those artifacts expire: after expiry, restore or reproduce the documented source inputs before rerunning. Do not silently replace a pinned source scene with a newer or unverified one.

## Earth Studio path

Shot setup is described in [EARTH_STUDIO.md](EARTH_STUDIO.md). Export an image-sequence ZIP with the original attribution intact, then process it locally:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Install ffmpeg separately.
python scripts/earth_studio_post.py \
  --input ~/Downloads/earth-studio-render.zip \
  --output output/coimbra_earthstudio_tiltshift.mp4 \
  --fps 30
```

The post-process keeps the framing, applies a tilted focus band and progressive blur, protects the attribution area, and encodes H.264. `--fps` must match the source project. A normal Google Drive sharing page is not a direct ZIP download URL for Actions.

## Attribution and credential boundary

Preserve all applicable source credits in published output, including Google/imagery-provider credits on the Earth Studio path, DGT and OpenStreetMap credits on the geodata path, and the existing Poly Haven acknowledgement where applicable. Do not crop or conceal required attribution.

Never commit tokens, passwords, sessions or authenticated source URLs. Source acquisition may use existing credential-consuming workflows; routine renderer work should not retrieve or relocate credential values. Preserve the generic APatch bridge and its protected-layer rules.

## Historical setup notes

The complete previous README is retained **byte-for-byte** in [README-PRE-CONSOLIDATION-2026-09-30.md](README-PRE-CONSOLIDATION-2026-09-30.md). It contains the earlier 001–008 setup chronology and command details. Its historical statements about which path was primary are not a description of current project routing.
